"""PostgreSQL-backed dispatch: business intents remain authoritative across queue retries."""

import argparse
import asyncio
from datetime import timedelta
from uuid import UUID

import procrastinate
import psycopg
from app.config import get_settings
from app.db import get_engine
from app.profile_models import Operation, now
from app.services.operations import process_operation
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

connection_string = get_settings().sqlalchemy_url().replace("postgresql+psycopg:", "postgresql:", 1)
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=connection_string, kwargs={"connect_timeout": 10}, min_size=1, max_size=5
    )
)


@app.task(name="jobfinder.operation", queue="ai")
def execute(operation_id: str) -> None:
    process_operation(UUID(operation_id))


def dispatch() -> int:
    count = 0
    with Session(get_engine()) as db, db.begin():
        expired = db.scalars(
            select(Operation)
            .where(Operation.state == "running", Operation.lease_until < now())
            .with_for_update(skip_locked=True)
            .limit(100)
        )
        for operation in expired:
            operation.state = "queued" if operation.attempts < 3 else "failed"
            operation.lease_token = None
            operation.dispatched_at = None
            operation.error_code = "worker_interrupted"
            operation.error_message = "The worker stopped before finishing this operation."
        pending = db.scalars(
            select(Operation)
            .where(
                Operation.state == "queued",
                Operation.available_at <= now(),
                or_(
                    Operation.dispatched_at.is_(None),
                    Operation.dispatched_at < now() - timedelta(minutes=2),
                ),
            )
            .order_by(Operation.created_at)
            .with_for_update(skip_locked=True)
            .limit(100)
        )
        for operation in pending:
            queue = (
                "ai"
                if operation.kind in {"profile_ingest", "ai_validate", "ai_reconcile"}
                else "fetch"
                if operation.kind in {"source_collect", "discovery_step"}
                else "control"
            )
            # Execution locks + the business lease make duplicate dispatch harmless.
            # Do not use a queueing lock: it can conflict with recovery of a stalled
            # "doing" job when a replacement "todo" job already exists.
            execute.configure(queue=queue, lock=f"operation:{operation.id}").defer(
                operation_id=str(operation.id)
            )
            operation.dispatched_at = now()
            count += 1
    return count


@app.periodic(cron="* * * * *")
@app.task(name="jobfinder.dispatch", queue="control")
def tick(timestamp: int) -> None:
    from app.collection.discovery import schedule
    from app.collection.inventory import schedule_due

    with Session(get_engine()) as db, db.begin():
        schedule_due(db)
    # Collection finalization locks company before source. Release scheduling
    # source locks before discovery takes company locks to avoid inversion.
    with Session(get_engine()) as db, db.begin():
        schedule(db)
    dispatch()


async def recover_stalled_jobs() -> int:
    stalled = await app.job_manager.get_stalled_jobs(
        task_name="jobfinder.operation", seconds_since_heartbeat=300
    )
    count = 0
    for job in stalled:
        await app.job_manager.retry_job(job)
        count += 1
    return count


@app.periodic(cron="*/5 * * * *")
@app.task(name="jobfinder.maintenance", queue="control")
async def maintenance(timestamp: int) -> None:
    from app.ai.provider import recover_reservations
    from app.services.retention import expire_approved_documents

    await recover_stalled_jobs()
    await asyncio.to_thread(recover_reservations)
    await asyncio.to_thread(expire_approved_documents)


def bootstrap_queue() -> None:
    # Use the queue library's schema, never reimplement queue internals in ORM migrations.
    with psycopg.connect(connection_string, autocommit=True, connect_timeout=10) as connection:
        connection.execute("SELECT pg_advisory_lock(1012002)")
        try:
            exists = connection.execute("SELECT to_regclass('procrastinate_jobs')").fetchone()
            if exists is not None and exists[0] is None:
                with app.open():
                    app.schema_manager.apply_schema()
        finally:
            connection.execute("SELECT pg_advisory_unlock(1012002)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Finder durable worker")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--queues", default="control,fetch,notify")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    if args.bootstrap:
        bootstrap_queue()
        return
    with app.open():
        dispatch()
    app.run_worker(
        queues=args.queues.split(","),
        concurrency=args.concurrency,
        fetch_job_polling_interval=2,
        shutdown_graceful_timeout=30,
        delete_jobs="successful",
    )


if __name__ == "__main__":
    main()
