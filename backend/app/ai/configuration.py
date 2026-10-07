from uuid import UUID

from app.ai.contracts import AiLimits, TaskKey
from app.ai.models import AiLimitsRow, TaskRevision
from sqlalchemy import select
from sqlalchemy.orm import Session


def latest(db: Session, task: TaskKey) -> TaskRevision | None:
    return db.scalar(
        select(TaskRevision)
        .where(TaskRevision.task == task)
        .order_by(TaskRevision.revision.desc())
        .limit(1)
    )


def capture(db: Session, task: TaskKey) -> str | None:
    row = latest(db, task)
    return str(row.id) if row else None


def limits(db: Session) -> tuple[int, AiLimits]:
    row = db.get(AiLimitsRow, 1)
    return (row.revision, AiLimits.model_validate(row.settings)) if row else (0, AiLimits())


def set_validation(config_id: UUID, state: str, error_code: str | None = None) -> None:
    from app.db import get_engine

    with Session(get_engine()) as db, db.begin():
        row = db.get(TaskRevision, config_id, with_for_update=True)
        if row:
            row.validation_state = state
            row.error_code = error_code
