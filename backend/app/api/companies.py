from typing import Annotated, Any
from uuid import UUID, uuid4

from app.api.contracts import OperationAccepted
from app.api.inventory_contracts import (
    CompanyEdit,
    CompanyInput,
    CompanyPage,
    CompanyView,
    DiscoveryChoice,
    DiscoveryView,
    RulesPreview,
    RunView,
    SourceEdit,
    SourceInput,
    SourceRulesEdit,
    SourceView,
)
from app.auth import DB, Auth
from app.collection.ats import request_url
from app.collection.contracts import public_link
from app.collection.inventory import key
from app.collection.models import CollectionRun, Company, DiscoveryRun, Source, SourceSnapshot
from app.collection.overview import company_views
from app.errors import problem
from app.profile_models import Operation, now
from app.services.operations import create_operation, operation_response, request_hash
from fastapi import APIRouter, Header, Query
from pydantic import ValidationError
from sqlalchemy import select

router = APIRouter(tags=["companies"])
Expected = Annotated[str | None, Header(alias="If-Match")]
Key = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]


def company_row(db: DB, identifier: UUID, *, lock: bool = False) -> Company:
    row = db.get(Company, identifier, with_for_update=lock)
    if row is None:
        raise problem(404, "company_not_found", "This company watch could not be found.")
    return row


def revision_check(expected: str | None, revision: int) -> None:
    if expected is None:
        raise problem(428, "revision_required", "Reload this item before saving changes.")
    if expected != f'"{revision}"':
        raise problem(
            409, "revision_conflict", "This item changed elsewhere. Your edits were not saved."
        )


@router.get("/companies", response_model=CompanyPage)
def companies(session: Auth, db: DB, offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Company).order_by(Company.created_at, Company.id).offset(offset).limit(21)
        )
    )
    return {
        "items": company_views(db, rows[:20]),
        "next_offset": offset + 20 if len(rows) > 20 else None,
    }


@router.post("/companies", response_model=OperationAccepted, status_code=202)
def add_company(
    body: CompanyInput, session: Auth, db: DB, idempotency_key: Key = None
) -> dict[str, str]:
    identifier = uuid4()
    operation = create_operation(
        db,
        "company_discover",
        idempotency_key or str(uuid4()),
        {"company_id": str(identifier)},
        request_hash(body.model_dump()),
    )
    identifier = UUID(operation.parameters["company_id"])
    if db.get(Company, identifier) is None:
        db.add(Company(id=identifier, **body.model_dump()))
    db.commit()
    return operation_response(operation, identifier)


@router.get("/companies/{identifier}", response_model=CompanyView)
def company(identifier: UUID, session: Auth, db: DB) -> CompanyView:
    return company_views(db, [company_row(db, identifier)])[0]


@router.patch("/companies/{identifier}", response_model=CompanyView)
def edit_company(
    identifier: UUID, body: CompanyEdit, session: Auth, db: DB, expected: Expected = None
) -> CompanyView:
    row = company_row(db, identifier, lock=True)
    revision_check(expected, row.revision)
    pause_changed = row.paused != body.paused
    website_changed = row.website != body.website
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    row.revision += 1
    if website_changed:
        row.resolution = "unresolved"
        row.discovery_due_at = now()
    if pause_changed:
        for source in db.scalars(
            select(Source).where(Source.company_id == row.id).with_for_update()
        ):
            source.revision += 1  # Discard results from requests dispatched before the pause.
            if not row.paused:
                source.next_due_at = now()
    db.commit()
    return company_views(db, [row])[0]


def queue_company(
    db: DB, identifier: UUID, kind: str, idempotency_key: str | None
) -> dict[str, str]:
    row = company_row(db, identifier, lock=True)
    if row.paused:
        raise problem(409, "company_paused", "Resume this company before checking it.")
    existing = db.scalar(
        select(Operation)
        .where(
            Operation.kind == kind,
            Operation.parameters["company_id"].astext == str(identifier),
            Operation.state.in_(["queued", "running"]),
        )
        .order_by(Operation.created_at)
        .limit(1)
    )
    # Explicit keys retain their own stable result and cannot be reused for another watch.
    # Unkeyed UI clicks join pending work; source-level fan-out deduplicates either path.
    operation = (
        create_operation(db, kind, idempotency_key, {"company_id": str(identifier)})
        if idempotency_key
        else existing or create_operation(db, kind, str(uuid4()), {"company_id": str(identifier)})
    )
    db.commit()
    return operation_response(operation, identifier)


@router.post("/companies/{identifier}/discover", response_model=OperationAccepted, status_code=202)
def discover(
    identifier: UUID, session: Auth, db: DB, idempotency_key: Key = None
) -> dict[str, str]:
    return queue_company(db, identifier, "company_discover", idempotency_key)


@router.post("/companies/{identifier}/check", response_model=OperationAccepted, status_code=202)
def check(identifier: UUID, session: Auth, db: DB, idempotency_key: Key = None) -> dict[str, str]:
    return queue_company(db, identifier, "company_check", idempotency_key)


@router.get("/companies/{identifier}/sources", response_model=list[SourceView])
def sources(identifier: UUID, session: Auth, db: DB) -> list[Source]:
    company_row(db, identifier)
    return list(
        db.scalars(select(Source).where(Source.company_id == identifier).order_by(Source.id))
    )


@router.post("/companies/{identifier}/sources", response_model=SourceView, status_code=201)
def add_source(identifier: UUID, body: SourceInput, session: Auth, db: DB) -> Source:
    company = company_row(db, identifier, lock=True)
    if body.adapter != "lever" and body.region != "global":
        raise problem(422, "invalid_region", "The EU region applies only to Lever sources.")
    url = request_url(body.adapter, body.board, region=body.region)
    identity = key(url)
    row = db.scalar(
        select(Source).where(Source.company_id == identifier, Source.identity == identity)
    )
    if row is None:
        row = Source(
            company_id=identifier,
            identity=identity,
            adapter=body.adapter,
            config={"board": body.board, "region": body.region},
            url=url,
            evidence={"basis": "owner_confirmed", "network_verified": False},
            interval_hours=body.interval_hours or company.interval_hours,
        )
        db.add(row)
    db.commit()
    return row


@router.patch("/sources/{identifier}", response_model=SourceView)
def edit_source(
    identifier: UUID, body: SourceEdit, session: Auth, db: DB, expected: Expected = None
) -> Source:
    row = db.get(Source, identifier, with_for_update=True)
    if row is None:
        raise problem(404, "source_not_found", "This source could not be found.")
    revision_check(expected, row.revision)
    row.enabled = body.enabled
    row.interval_hours = body.interval_hours
    row.revision += 1
    if row.enabled:
        row.next_due_at = now()
    db.commit()
    return row


def rules_source(db: DB, identifier: UUID, expected: str | None) -> Source:
    row = db.get(Source, identifier, with_for_update=True)
    if row is None:
        raise problem(404, "source_not_found", "This source could not be found.")
    revision_check(expected, row.revision)
    if row.adapter != "generic_http" or row.authoritative:
        raise problem(
            422, "source_rules_unsupported", "Extraction rules apply to website sources only."
        )
    return row


@router.put("/sources/{identifier}/rules", response_model=SourceView)
def update_rules(
    identifier: UUID, body: SourceRulesEdit, session: Auth, db: DB, expected: Expected = None
) -> Source:
    row = rules_source(db, identifier, expected)
    config = dict(row.config)
    if body.rules is None:
        config.pop("rules", None)
    else:
        config["rules"] = body.rules.model_dump(mode="json")
    row.config = config
    row.revision += 1
    if row.enabled:
        row.next_due_at = now()
    db.commit()
    return row


@router.post("/sources/{identifier}/rules/preview", response_model=RulesPreview)
def preview_rules(
    identifier: UUID, body: SourceRulesEdit, session: Auth, db: DB, expected: Expected = None
) -> RulesPreview:
    from datetime import timedelta

    from app.collection.generic_inventory import collect
    from app.fetcher.contracts import FetchResult

    row = rules_source(db, identifier, expected)
    snapshot = db.get(SourceSnapshot, (row.id, key(row.url)))
    if snapshot is None or snapshot.fetched_at < now() - timedelta(days=7):
        raise problem(
            409,
            "source_preview_unavailable",
            "No recent saved source page is available. Run a company check first.",
        )
    try:
        document = FetchResult.model_validate(snapshot.document)
    except ValidationError:
        raise problem(
            409, "source_preview_unavailable", "The saved source page is invalid. Run a new check."
        ) from None
    if (
        document.url != row.url
        or document.status != 200
        or document.content_type.split(";", 1)[0].lower().strip()
        not in {"text/html", "application/xhtml+xml"}
        or snapshot.body_hash != key(document.body)
    ):
        raise problem(
            409,
            "source_preview_unavailable",
            "The saved source page is unavailable. Run a new check.",
        )
    page = collect(
        row.url,
        row.config["company_name"],
        row.config["website"],
        document=document,
        rules=body.rules,
    )
    return RulesPreview(
        fetched_at=snapshot.fetched_at,
        accepted_jobs=len(page.postings),
        examples=[job.title for job in page.postings[:10]],
        complete=page.complete,
        issues=page.issues,
    )


@router.get("/sources/{identifier}/runs", response_model=list[RunView])
def runs(
    identifier: UUID, session: Auth, db: DB, offset: int = Query(0, ge=0)
) -> list[CollectionRun]:
    if db.get(Source, identifier) is None:
        raise problem(404, "source_not_found", "This source could not be found.")
    return list(
        db.scalars(
            select(CollectionRun)
            .where(CollectionRun.source_id == identifier)
            .order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc())
            .offset(offset)
            .limit(20)
        )
    )


@router.get("/companies/{identifier}/discovery", response_model=list[DiscoveryView])
def discovery_history(
    identifier: UUID, session: Auth, db: DB, offset: int = Query(0, ge=0)
) -> list[DiscoveryRun]:
    company_row(db, identifier)
    return list(
        db.scalars(
            select(DiscoveryRun)
            .where(DiscoveryRun.company_id == identifier)
            .order_by(DiscoveryRun.started_at.desc(), DiscoveryRun.id.desc())
            .offset(offset)
            .limit(20)
        )
    )


@router.post(
    "/companies/{identifier}/discovery/{run_id}/confirm",
    response_model=OperationAccepted,
    status_code=202,
)
def confirm_discovery(
    identifier: UUID,
    run_id: UUID,
    body: DiscoveryChoice,
    session: Auth,
    db: DB,
    expected: Expected = None,
) -> dict[str, str]:
    company = company_row(db, identifier, lock=True)
    revision_check(expected, company.revision)
    run = db.get(DiscoveryRun, run_id)
    if run is None or run.company_id != company.id:
        raise problem(404, "discovery_not_found", "This discovery run could not be found.")
    if company.paused or run.company_revision != company.revision:
        raise problem(409, "discovery_changed", "Refresh discovery before confirming this company.")
    if not any(
        candidate.get("url") == body.url and candidate.get("status") == "needs_identity_review"
        for candidate in run.candidates
    ):
        raise problem(422, "invalid_candidate", "Choose a company page from these search results.")
    company.website = public_link(body.url)
    company.revision += 1
    company.resolution = "unresolved"
    company.discovery_due_at = now()
    company.evidence = {
        **company.evidence,
        "owner_selected_candidate": body.url,
        "owner_selected_run_id": str(run.id),
    }
    operation = create_operation(
        db, "company_discover", str(uuid4()), {"company_id": str(company.id)}
    )
    db.commit()
    return operation_response(operation, company.id)
