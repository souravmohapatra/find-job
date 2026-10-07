from typing import Any
from uuid import UUID

from app.api.contracts import OperationView
from app.auth import DB, Auth
from app.errors import problem
from app.profile_models import Document, Operation, ProfileDraft, now
from fastapi import APIRouter
from sqlalchemy import select, text

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/{operation_id}", response_model=OperationView)
def get_operation(operation_id: UUID, session: Auth, db: DB) -> dict[str, Any]:
    operation = db.get(Operation, operation_id)
    if operation is None:
        raise problem(404, "operation_not_found", "This operation could not be found.")
    return {
        "id": operation.id,
        "kind": operation.kind,
        "state": operation.state,
        "progress": operation.progress,
        "attempts": operation.attempts,
        "error_code": operation.error_code,
        "error_message": operation.error_message,
        "created_at": operation.created_at,
        "finished_at": operation.finished_at,
    }


@router.post("/{operation_id}/retry", status_code=202)
def retry_operation(operation_id: UUID, session: Auth, db: DB) -> dict[str, str]:
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    operation = db.get(Operation, operation_id, with_for_update=True)
    if operation is None:
        raise problem(404, "operation_not_found", "This operation could not be found.")
    if operation.state not in {"failed", "blocked"}:
        raise problem(
            409, "operation_not_retryable", "Only failed or blocked operations can be retried."
        )
    if operation.kind == "profile_ingest":
        identifier = UUID(operation.parameters["document_id"])
        document = db.get(Document, identifier)
        draft = db.scalar(select(ProfileDraft).where(ProfileDraft.document_id == identifier))
        if document is None or document.deleted_at or draft is None:
            raise problem(409, "document_deleted", "Upload a new document to continue.")
        document.status = "queued"
        draft.status = "processing"
    operation.state = "queued"
    operation.attempts = 0
    operation.available_at = now()
    operation.dispatched_at = None
    operation.error_code = operation.error_message = None
    operation.progress = "Waiting to retry"
    db.commit()
    return {"operation_id": str(operation.id), "status_url": f"/api/v1/operations/{operation.id}"}
