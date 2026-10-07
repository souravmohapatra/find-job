"""Batched company coverage summaries; inventory counts never imply market coverage."""

from app.api.inventory_contracts import CompanyCoverage, CompanyView
from app.collection.models import CollectionRun, Company, Job, Source
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def company_views(db: Session, companies: list[Company]) -> list[CompanyView]:
    if not companies:
        return []
    identifiers = [company.id for company in companies]
    summaries = {identifier: CompanyCoverage() for identifier in identifiers}
    for company_id, availability, count in db.execute(
        select(Job.company_id, Job.availability, func.count())
        .where(Job.company_id.in_(identifiers))
        .group_by(Job.company_id, Job.availability)
    ):
        summary = summaries[company_id]
        summary.collected_jobs += count
        setattr(summary, availability + "_jobs", count)
    for source in db.scalars(select(Source).where(Source.company_id.in_(identifiers))):
        summary = summaries[source.company_id]
        summary.sources += 1
        if source.last_success_at:
            summary.last_success_at = max(
                summary.last_success_at or source.last_success_at, source.last_success_at
            )
        if not source.enabled:
            continue
        summary.enabled_sources += 1
        summary.partial_sources += int(not source.authoritative)
        summary.sources_needing_attention += int(source.last_error is not None)
        summary.sources_without_success += int(source.last_success_at is None)
        due = max(source.next_due_at, source.cooldown_until or source.next_due_at)
        summary.next_check_at = min(summary.next_check_at or due, due)
    for company_id, attempted_at in db.execute(
        select(Source.company_id, func.max(CollectionRun.started_at))
        .join(CollectionRun, CollectionRun.source_id == Source.id)
        .where(Source.company_id.in_(identifiers))
        .group_by(Source.company_id)
    ):
        summaries[company_id].last_attempt_at = attempted_at
    result = []
    for company in companies:
        summary = summaries[company.id]
        if company.paused:
            summary.next_check_at = None
        else:
            summary.next_discovery_at = company.discovery_due_at
        result.append(
            CompanyView(
                id=company.id,
                label=company.label,
                website=company.website,
                interval_hours=company.interval_hours,
                paused=company.paused,
                revision=company.revision,
                resolution=company.resolution,
                created_at=company.created_at,
                coverage=summary,
            )
        )
    return result
