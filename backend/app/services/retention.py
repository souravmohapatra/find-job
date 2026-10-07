from datetime import timedelta

from app.config import get_settings
from app.db import get_engine
from app.profile_models import Document, ProfileDraft, now
from sqlalchemy import select, text
from sqlalchemy.orm import Session


def expire_approved_documents() -> int:
    """Remove old originals/raw text while retaining approved facts and evidence excerpts."""
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
        documents = list(
            db.scalars(
                select(Document)
                .join(ProfileDraft)
                .where(
                    Document.approved_at <= now() - timedelta(days=30),
                    Document.retain_original.is_(False),
                    Document.deleted_at.is_(None),
                    ProfileDraft.status == "activated",
                )
                .with_for_update(of=Document)
                .limit(100)
            )
        )
        for document in documents:
            (get_settings().document_dir / document.storage_key).unlink(missing_ok=True)
            document.spans = None
            document.deleted_at = now()
            document.status = "expired"
        return len(documents)


def expire_page_extractions() -> int:
    """Discard public-page diagnostic snapshots after seven days; epochs expire after one day."""
    from app.collection.models import PageExtraction

    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
        rows = list(
            db.scalars(
                select(PageExtraction)
                .where(PageExtraction.created_at < now() - timedelta(days=7))
                .order_by(PageExtraction.created_at)
                .limit(100)
            )
        )
        for row in rows:
            db.delete(row)
        return len(rows)
