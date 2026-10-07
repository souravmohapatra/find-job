"""A queue consumer can run before the dispatcher's business transaction commits."""

from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep

from app.db import get_engine
from app.profile_models import Operation
from app.services.operations import create_operation, process_operation
from sqlalchemy import select, text
from sqlalchemy.orm import Session


def test_claim_waits_for_dispatch_row_lock_instead_of_dropping_queue_job():
    with Session(get_engine()) as db, db.begin():
        identifier = create_operation(db, "profile_reassess", "dispatch-lock-race", {}).id
    with ThreadPoolExecutor(max_workers=1) as pool, Session(get_engine()) as dispatcher:
        dispatcher.scalar(select(Operation).where(Operation.id == identifier).with_for_update())
        future = pool.submit(process_operation, identifier)
        waiting = False
        try:
            deadline = monotonic() + 5
            while monotonic() < deadline and not future.done():
                with get_engine().connect() as observer:
                    waiting = bool(
                        observer.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE datname=current_database() AND wait_event_type='Lock' "
                                "AND query LIKE '%operation_intents%')"
                            )
                        )
                    )
                if waiting:
                    break
                sleep(0.01)
            assert waiting and not future.done(), "A locked existing intent is not a missing intent"
        finally:
            dispatcher.commit()
            future.result(timeout=10)
    with Session(get_engine()) as db:
        result = db.get(Operation, identifier)
        assert result.state == "succeeded" and result.attempts == 1
