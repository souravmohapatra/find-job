import hashlib
import os
from typing import Annotated, Any
from uuid import UUID, uuid4

from app.ai.configuration import capture
from app.api.contracts import (
    DocumentPage,
    DraftView,
    OperationAccepted,
    ProfileSnapshot,
    ProfileView,
)
from app.auth import DB, Auth
from app.config import get_settings
from app.documents.parser import DocumentError, detect_type
from app.domain.profile import Facts, Preferences, ProfileInput, experience
from app.errors import problem
from app.profile_models import Document, Operation, Profile, ProfileDraft, ProfileRevision, now
from app.services.operations import create_operation, operation_response, request_hash
from app.services.profiles import validate_review
from fastapi import APIRouter, File, Form, Header, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert

router = APIRouter(prefix="/profile", tags=["profile"])
Expected = Annotated[str | None, Header(alias="If-Match")]
Key = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]


def lock_profile(db: DB) -> Profile:
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    db.execute(insert(Profile).values(id=1, current_revision=0).on_conflict_do_nothing())
    profile = db.get(Profile, 1, with_for_update=True)
    assert profile is not None
    return profile


def expect_revision(expected: str | None, current: int) -> None:
    if expected is None:
        raise problem(428, "revision_required", "Reload the profile before saving changes.")
    if expected != f'"{current}"':
        raise problem(
            409,
            "revision_conflict",
            "This profile changed elsewhere. Your edits have not been saved.",
        )


def revision_data(revision: ProfileRevision | None) -> dict[str, Any]:
    return {
        "revision": revision.revision if revision else 0,
        "revision_id": revision.id if revision else None,
        "facts": revision.facts if revision else Facts().model_dump(mode="json"),
        "preferences": revision.preferences if revision else Preferences().model_dump(mode="json"),
        "experience": experience(Facts.model_validate(revision.facts)) if revision else None,
    }


def document_operation(db: DB, document_id: UUID) -> UUID | None:
    return db.scalar(
        select(Operation.id)
        .where(
            Operation.kind == "profile_ingest",
            Operation.parameters["document_id"].astext == str(document_id),
        )
        .limit(1)
    )


@router.get("", response_model=ProfileView)
def get_profile(session: Auth, db: DB, response: Response) -> dict[str, Any]:
    profile = db.get(Profile, 1)
    revision = (
        db.scalar(
            select(ProfileRevision).where(
                ProfileRevision.profile_id == 1,
                ProfileRevision.revision == profile.current_revision,
            )
        )
        if profile
        else None
    )
    response.headers["ETag"] = f'"{profile.current_revision if profile else 0}"'
    drafts = db.scalars(
        select(ProfileDraft)
        .where(ProfileDraft.status != "activated")
        .order_by(ProfileDraft.created_at.desc())
        .limit(20)
    )
    return {
        **revision_data(revision),
        "revision": profile.current_revision if profile else 0,
        "drafts": [
            {
                "id": d.id,
                "operation_id": document_operation(db, d.document_id),
                "status": d.status,
                "document_id": d.document_id,
                "created_at": d.created_at,
            }
            for d in drafts
        ],
    }


@router.get("/documents", response_model=DocumentPage)
def list_documents(session: Auth, db: DB, offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Document)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset(offset)
            .limit(21)
        )
    )
    return {
        "documents": [
            {
                "id": row.id,
                "media_type": row.media_type,
                "size": row.size,
                "status": row.status,
                "retain_original": row.retain_original,
                "created_at": row.created_at,
                "approved_at": row.approved_at,
                "deleted_at": row.deleted_at,
            }
            for row in rows[:20]
        ],
        "next_offset": offset + 20 if len(rows) > 20 else None,
    }


class RetentionChange(BaseModel):
    retain_original: bool


@router.patch("/documents/{document_id}/retention", status_code=204)
def update_retention(document_id: UUID, body: RetentionChange, session: Auth, db: DB) -> None:
    lock_profile(db)
    document = db.get(Document, document_id, with_for_update=True)
    if document is None or document.deleted_at:
        raise problem(404, "document_not_found", "The original document is no longer available.")
    document.retain_original = body.retain_original
    db.commit()


@router.post("/documents", status_code=202, response_model=OperationAccepted)
def upload_document(
    session: Auth,
    db: DB,
    file: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form()] = False,
    retain_original: Annotated[bool, Form()] = False,
    idempotency_key: Key = None,
) -> dict[str, str]:
    if get_settings().integration_mode == "live" and not consent:
        raise problem(
            422,
            "consent_required",
            "Confirm that extracted CV text may be sent to OpenRouter and its provider.",
        )
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise problem(413, "document_too_large", "Upload a CV of at most 10 MiB.")
    if not content:
        raise problem(422, "empty_document", "The uploaded file is empty.")
    try:
        media_type = detect_type(content)
    except DocumentError as error:
        raise problem(422, "unsupported_document", str(error)) from error
    profile = lock_profile(db)
    identifier = uuid4()
    fingerprint = request_hash(
        {
            "sha256": hashlib.sha256(content).hexdigest(),
            "retain_original": retain_original,
            "consent": consent,
        }
    )
    operation = create_operation(
        db,
        "profile_ingest",
        idempotency_key or str(uuid4()),
        {
            "document_id": str(identifier),
            "ai_config_id": capture(db, "profile_analysis"),
            "consent": consent,
            "integration_mode": get_settings().integration_mode,
        },
        fingerprint,
    )
    if operation.parameters["document_id"] != str(identifier):
        db.commit()
        return operation_response(operation, UUID(operation.parameters["document_id"]))
    current = db.scalar(
        select(ProfileRevision).where(
            ProfileRevision.profile_id == 1, ProfileRevision.revision == profile.current_revision
        )
    )
    directory = get_settings().document_dir
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / str(identifier)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        document = Document(
            id=identifier,
            storage_key=str(identifier),
            media_type=media_type,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            retain_original=retain_original,
        )
        db.add(document)
        db.flush()
        db.add(
            ProfileDraft(
                document_id=identifier,
                base_revision=profile.current_revision,
                preferences=current.preferences
                if current
                else Preferences().model_dump(mode="json"),
            )
        )
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return operation_response(operation, identifier)


@router.get("/drafts/{draft_id}", response_model=DraftView)
def get_draft(draft_id: UUID, session: Auth, db: DB, response: Response) -> dict[str, Any]:
    draft = db.get(ProfileDraft, draft_id)
    if draft is None:
        raise problem(404, "draft_not_found", "This draft could not be found.")
    document = db.get(Document, draft.document_id)
    base = db.scalar(
        select(ProfileRevision).where(
            ProfileRevision.profile_id == 1, ProfileRevision.revision == draft.base_revision
        )
    )
    response.headers["ETag"] = f'"{draft.version}"'
    return {
        "id": draft.id,
        "operation_id": document_operation(db, draft.document_id),
        "document_id": draft.document_id,
        "status": draft.status,
        "version": draft.version,
        "base_revision": draft.base_revision,
        "facts": draft.facts,
        "preferences": draft.preferences,
        "base_profile": {**revision_data(base), "revision": draft.base_revision},
        "document_available": bool(document and not document.deleted_at),
        "spans": document.spans if document else None,
    }


@router.patch("/drafts/{draft_id}", response_model=DraftView)
def edit_draft(
    draft_id: UUID,
    body: ProfileInput,
    session: Auth,
    db: DB,
    response: Response,
    if_match: Expected = None,
) -> dict[str, Any]:
    lock_profile(db)
    draft = db.get(ProfileDraft, draft_id, with_for_update=True)
    if draft is None:
        raise problem(404, "draft_not_found", "This draft could not be found.")
    expect_revision(if_match, draft.version)
    if draft.status != "review":
        raise problem(409, "draft_not_editable", "Wait for processing or start a new draft.")
    draft.facts = body.facts.model_dump(mode="json")
    draft.preferences = body.preferences.model_dump(mode="json")
    draft.version += 1
    db.commit()
    return get_draft(draft_id, session, db, response)


class Activation(BaseModel):
    draft_version: int
    reviewed: bool


def activate_revision(db: DB, profile: Profile, body: ProfileInput) -> ProfileRevision:
    revision = ProfileRevision(
        profile_id=1,
        revision=profile.current_revision + 1,
        facts=body.facts.model_dump(mode="json"),
        preferences=body.preferences.model_dump(mode="json"),
    )
    db.add(revision)
    db.flush()
    profile.current_revision = revision.revision
    create_operation(
        db, "profile_reassess", str(revision.id), {"profile_revision_id": str(revision.id)}
    )
    return revision


@router.post("/drafts/{draft_id}/activate", response_model=ProfileSnapshot)
def activate_draft(
    draft_id: UUID,
    body: Activation,
    session: Auth,
    db: DB,
    response: Response,
    if_match: Expected = None,
) -> dict[str, Any]:
    profile = lock_profile(db)
    expect_revision(if_match, profile.current_revision)
    draft = db.get(ProfileDraft, draft_id, with_for_update=True)
    if draft is None:
        raise problem(404, "draft_not_found", "This draft could not be found.")
    if (
        draft.status != "review"
        or draft.base_revision != profile.current_revision
        or draft.version != body.draft_version
    ):
        raise problem(
            409,
            "draft_conflict",
            "The draft or approved profile changed. Compare your edits before saving.",
        )
    if not body.reviewed:
        raise problem(
            422, "review_required", "Confirm that you reviewed the profile before activating it."
        )
    document = db.get(Document, draft.document_id, with_for_update=True)
    profile_input = ProfileInput(
        facts=Facts.model_validate(draft.facts),
        preferences=Preferences.model_validate(draft.preferences),
    )
    validate_review(profile_input, document)
    revision = activate_revision(db, profile, profile_input)
    draft.status = "activated"
    draft.version += 1
    if document:
        document.approved_at = now()
    db.commit()
    response.headers["ETag"] = f'"{revision.revision}"'
    return revision_data(revision)


@router.patch("", response_model=ProfileSnapshot)
def update_profile(
    body: ProfileInput, session: Auth, db: DB, response: Response, if_match: Expected = None
) -> dict[str, Any]:
    profile = lock_profile(db)
    expect_revision(if_match, profile.current_revision)
    validate_review(body)
    revision = activate_revision(db, profile, body)
    db.commit()
    response.headers["ETag"] = f'"{revision.revision}"'
    return revision_data(revision)


@router.get("/documents/{document_id}/download")
def download_document(document_id: UUID, session: Auth, db: DB) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at:
        raise problem(404, "document_not_found", "The original document is no longer available.")
    path = get_settings().document_dir / document.storage_key
    if not path.is_file():
        raise problem(404, "document_not_found", "The original document is no longer available.")
    extension = (
        ".pdf"
        if document.media_type == "application/pdf"
        else ".txt"
        if document.media_type == "text/plain"
        else ".docx"
    )
    return FileResponse(path, media_type="application/octet-stream", filename="cv" + extension)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID, session: Auth, db: DB) -> None:
    lock_profile(db)
    document = db.get(Document, document_id, with_for_update=True)
    if document is None:
        raise problem(404, "document_not_found", "This document could not be found.")
    (get_settings().document_dir / document.storage_key).unlink(missing_ok=True)
    document.spans = None
    document.deleted_at = now()
    document.status = "deleted"
    db.execute(
        update(Operation)
        .where(
            Operation.kind == "profile_ingest",
            Operation.parameters["document_id"].astext == str(document_id),
            Operation.state.in_(["queued", "running", "blocked", "failed"]),
        )
        .values(state="cancelled", lease_token=None, progress="Original document deleted")
    )
    draft = db.scalar(select(ProfileDraft).where(ProfileDraft.document_id == document_id))
    if draft and draft.status in {"processing", "blocked", "failed"}:
        draft.status = "cancelled"
    db.commit()


class PurgeConfirmation(BaseModel):
    confirmation: str


@router.post("/purge", status_code=204)
def purge_profile(body: PurgeConfirmation, session: Auth, db: DB) -> None:
    if body.confirmation != "DELETE PROFILE":
        raise problem(
            422,
            "confirmation_required",
            "Type DELETE PROFILE to confirm removal of the profile and its documents.",
        )
    profile = lock_profile(db)
    documents = list(db.scalars(select(Document)))
    db.execute(
        update(Operation)
        .where(
            Operation.kind.in_(["profile_ingest", "profile_reassess"]),
            Operation.state.in_(["queued", "running", "blocked"]),
        )
        .values(state="cancelled", lease_token=None)
    )
    for document in documents:
        (get_settings().document_dir / document.storage_key).unlink(missing_ok=True)
    db.execute(delete(ProfileDraft))
    db.execute(delete(Document))
    db.execute(delete(ProfileRevision))
    profile.current_revision += 1
    db.commit()
