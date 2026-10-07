import base64
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.api.inventory_contracts import Availability, JobDetail, JobPage, JobView
from app.auth import DB, Auth
from app.collection.models import Company, Job, JobRevision, JobSource, Source
from app.errors import problem
from app.services.operations import request_hash
from fastapi import APIRouter, Query
from sqlalchemy import func, select, tuple_

router = APIRouter(prefix="/jobs", tags=["jobs"])


def job_view(job: Job, revision: JobRevision, label: str) -> JobView:
    return JobView(
        id=job.id,
        company_id=job.company_id,
        company_label=label,
        revision_id=revision.id,
        revision=revision.revision,
        availability=job.availability,
        baseline=job.baseline,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        posting=revision.posting,
    )


@router.get("", response_model=JobPage)
def jobs(
    session: Auth,
    db: DB,
    company_id: UUID | None = None,
    view: Literal["all", "recommended"] = "recommended",
    availability: Availability = "active",
    q: str = Query("", max_length=200),
    limit: int = Query(30, ge=1, le=100),
    cursor: str | None = Query(None, max_length=1000),
) -> JobPage:
    if view == "recommended":
        raise problem(
            503,
            "matching_unavailable",
            "Shortlisting is not available yet. Browse all collected jobs.",
        )
    statement = (
        select(Job, JobRevision, Company.label)
        .join(
            JobRevision,
            (JobRevision.job_id == Job.id) & (JobRevision.revision == Job.current_revision),
        )
        .join(Company, Company.id == Job.company_id)
    )
    if company_id:
        if db.get(Company, company_id) is None:
            raise problem(404, "company_not_found", "This company watch could not be found.")
        statement = statement.where(Job.company_id == company_id)
    if availability != "all":
        statement = statement.where(Job.availability == availability)
    if q.strip():
        document = func.concat_ws(
            " ",
            Company.label,
            JobRevision.posting["title"].astext,
            JobRevision.posting["description"].astext,
        )
        statement = statement.where(
            func.to_tsvector("simple", document).op("@@")(
                func.plainto_tsquery("simple", q.strip()),
            )
        )
    filters = request_hash([company_id, availability, q.strip(), view])
    if cursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor))
            timestamp = datetime.fromisoformat(payload["seen"])
            identifier = UUID(payload["id"])
            if payload["filters"] != filters or timestamp.tzinfo is None:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise problem(
                422, "invalid_cursor", "Reload the list after changing its filters."
            ) from None
        statement = statement.where(
            tuple_(Job.first_seen_at, Job.id) < tuple_(timestamp, identifier)
        )
    rows = db.execute(
        statement.order_by(Job.first_seen_at.desc(), Job.id.desc()).limit(limit + 1)
    ).all()
    items = [job_view(job, revision, label) for job, revision, label in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "seen": last.first_seen_at.isoformat(),
                    "id": str(last.id),
                    "filters": filters,
                }
            ).encode()
        ).decode()
    return JobPage(items=items, next_cursor=next_cursor)


@router.get("/{identifier}", response_model=JobDetail)
def job_detail(identifier: UUID, session: Auth, db: DB) -> JobDetail:
    row = db.execute(
        select(Job, JobRevision, Company.label)
        .join(
            JobRevision,
            (JobRevision.job_id == Job.id) & (JobRevision.revision == Job.current_revision),
        )
        .join(Company, Company.id == Job.company_id)
        .where(Job.id == identifier)
    ).first()
    if row is None:
        raise problem(404, "job_not_found", "This collected job could not be found.")
    job, revision, label = row
    sources = list(
        db.scalars(
            select(Source)
            .join(JobSource, JobSource.source_id == Source.id)
            .where(JobSource.job_id == identifier)
            .distinct()
            .order_by(Source.id)
        )
    )
    return JobDetail(
        **job_view(job, revision, label).model_dump(),
        sources=sources,
        revision_count=job.current_revision,
    )
