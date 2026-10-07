import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.db import get_engine
from app.domain.profile import Evidence, Facts, ProfileInput, Span, validate_evidence
from app.profile_models import Document, ProfileDraft
from app.services.operations import OperationError
from sqlalchemy import select
from sqlalchemy.orm import Session


def redacted_spans(spans: list[Span]) -> list[Span]:
    result: list[Span] = []
    for span in spans:
        text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", span.text)
        parts = re.split(
            r"(\b(?:19|20)\d{2}[-/]\d{2}(?:[-/]\d{2})?\b"
            r"|\b(?:19|20)\d{2}[ \t]*[-–][ \t]*(?:19|20)\d{2}\b)",
            text,
        )
        # Do not join digits across document lines or mistake employment dates for phones.
        text = "".join(
            part
            if index % 2
            else re.sub(r"(?<!\w)(?:\+?\d[ \t().-]*){9,15}(?!\w)", "[phone removed]", part)
            for index, part in enumerate(parts)
        )
        text = re.sub(
            r"https?://(?:www\.)?(?:linkedin\.com/in|facebook\.com|instagram\.com)/\S+",
            "[personal link removed]",
            text,
            flags=re.I,
        )
        if re.match(r"\s*(?:date of birth|dob|home address|address)\s*:", text, flags=re.I):
            text = "[personal details removed]"
        result.append(span.model_copy(update={"text": text}))
    return result


def analyze_document(
    document_id: UUID, operation_id: UUID | None = None, parameters: dict[str, Any] | None = None
) -> dict[str, Any]:
    with Session(get_engine()) as db:
        document = db.get(Document, document_id)
        if document is None or document.deleted_at:
            raise OperationError("document_deleted", "This document has been deleted.")
        path = get_settings().document_dir / document.storage_key
        media_type = document.media_type
    try:
        parsed = subprocess.run(
            [sys.executable, "-m", "app.documents.parser", str(path), media_type],
            cwd=Path(__file__).resolve().parents[2],
            env={"LANG": "C.UTF-8"},
            capture_output=True,
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise OperationError(
            "parser_timeout", "The document took too long to read. Try a simpler file."
        ) from error
    try:
        data = json.loads(parsed.stdout)
    except (ValueError, UnicodeDecodeError) as error:
        raise OperationError(
            "parser_failed", "The document could not be read within the resource limits."
        ) from error
    if parsed.returncode:
        raise OperationError(
            "invalid_document", data.get("error", "The document could not be read.")
        )
    spans = [Span.model_validate(span) for span in data["spans"]]
    safe_spans = redacted_spans(spans)
    parameters = parameters or {}
    if get_settings().integration_mode == "live":
        if not parameters.get("consent") or parameters.get("integration_mode") != "live":
            raise OperationError(
                "consent_required",
                "Upload again and consent to external analysis before processing in live mode.",
                blocked=True,
            )
        from app.ai.profile import analyze_profile

        facts = analyze_profile(safe_spans, parameters.get("ai_config_id"), operation_id)
    else:
        # Explicit mock, derived only from submitted text; no invented career or qualifications.
        first = next((span for span in safe_spans if "removed]" not in span.text), safe_spans[0])
        facts = Facts(
            summary=first.text[:5000],
            summary_evidence=[Evidence(span_id=first.id, quote=first.text[:1000])],
        )
    validate_evidence(facts, safe_spans)
    return {
        "spans": [span.model_dump() for span in safe_spans],
        "facts": facts.model_dump(mode="json"),
    }


def save_analysis(db: Session, document_id: UUID, result: dict[str, Any]) -> None:
    document = db.get(Document, document_id, with_for_update=True)
    draft = db.scalar(
        select(ProfileDraft).where(ProfileDraft.document_id == document_id).with_for_update()
    )
    if document is None or document.deleted_at or draft is None or draft.status != "processing":
        raise OperationError(
            "document_changed", "The draft was deleted or changed during processing."
        )
    document.spans = result["spans"]
    document.status = "ready"
    draft.facts = result["facts"]
    draft.status = "review"


def validate_review(body: ProfileInput, document: Document | None = None) -> None:
    try:
        body.require_reviewed()
        if document and document.spans:
            validate_evidence(body.facts, [Span.model_validate(span) for span in document.spans])
    except ValueError as error:
        from app.errors import problem

        raise problem(422, "invalid_profile", str(error)) from error
