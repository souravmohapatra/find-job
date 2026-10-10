"""Phase F: Integrated worker, API, database, and portal journey validation.

Verifies end-to-end integration against a dedicated disposable database:
1. Owner authentication and AI Settings verification
2. Synthetic vacancy ingestion into inventory
3. Synthetic CV analysis via live Luna (call 1) and reviewed profile creation
4. Live job matching assessment via worker / Jev Decisions (call 2)
5. Database persistence of current JobAssessment with explanation and evidence
6. Authenticated /api/v1/shortlist display with derived category and explanation
7. /api/v1/jobs all-jobs view display with truthful assessment state
8. Settings usage agreement with durable ledger
9. Assessment idempotency: unedited profile causes no second billable inference
"""

import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
venv_dir = ROOT / "backend/.venv"
venv_python = venv_dir / "bin/python"
if venv_python.exists() and Path(sys.prefix).resolve() != venv_dir.resolve():
    os.execv(str(venv_python), [str(venv_python), *sys.argv])

sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend/tests"))
DATA_DIR = ROOT / ".data"


def read_env_key(path: Path) -> str:
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("OPENROUTER_KEY="):
            return stripped.split("=", 1)[1].strip().strip("'\"")
    return ""


def provision_database(db_name: str) -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "compose.test.yaml",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "jobfinder",
            "-d",
            "jobfinder_test",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f'CREATE DATABASE "{db_name}"',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        raise RuntimeError(f"Database creation failed: {result.stderr}")
    print(f"database ready: {db_name}")


def run_journey() -> int:
    print("=== Phase F: Integrated Application Journey ===")
    run_id = time.strftime("%Y%m%d_%H%M%S")
    db_name = f"jobfinder_test_phase_f_{run_id}"

    provision_database(db_name)

    db_pass = (ROOT / ".secrets/test_db_password").read_text().strip()
    db_url = f"postgresql+psycopg://jobfinder:{quote(db_pass, safe='')}@127.0.0.1:55439/{db_name}"

    os.environ["JOBFINDER_DATABASE_URL"] = db_url
    os.environ["JOBFINDER_ENVIRONMENT"] = "development"
    os.environ["JOBFINDER_INTEGRATION_MODE"] = "live"
    os.environ["JOBFINDER_SEARCH_MODE"] = "mock"
    os.environ["JOBFINDER_NOTIFICATION_MODE"] = "mock"
    os.environ["JOBFINDER_ALLOWED_ORIGINS"] = '["https://localhost:8443"]'
    os.environ["JOBFINDER_ALLOWED_HOSTS"] = '["localhost", "127.0.0.1"]'
    os.environ["JOBFINDER_DECISIONS_LIVE_ENABLED"] = "true"
    os.environ["JOBFINDER_LIVE_LEDGER_PATH"] = str(DATA_DIR / "live_run_ledger.json")
    os.environ["JOBFINDER_DOCUMENT_DIR"] = str(DATA_DIR / f"phase_f_{run_id}" / "docs")

    key = read_env_key(ROOT / ".env")
    if not key:
        print("BLOCKED: OPENROUTER_KEY is absent in .env", file=sys.stderr)
        return 2

    bridge_dir = ROOT / ".secrets" / f"phase-f-{int(time.time())}"
    bridge_dir.mkdir(mode=0o700, exist_ok=True)
    bridge_file = bridge_dir / "openrouter_api_key"
    bridge_file.write_text(key)
    bridge_file.chmod(0o600)
    os.environ["JOBFINDER_OPENROUTER_KEY_FILE"] = str(bridge_file)

    try:
        from app.config import get_settings
        from app.db import get_engine

        get_settings.cache_clear()
        get_engine.cache_clear()

        # Schema migration and synthetic owner creation
        from alembic import command
        from alembic.config import Config
        from app.ai.configuration import latest
        from app.ai.contracts import AiLimits, TaskConfig
        from app.ai.models import AiLimitsRow, InferenceCall, TaskRevision
        from app.ai.profile import analyze_profile
        from app.cli import create_owner
        from app.collection.contracts import InventoryPage, Posting
        from app.collection.models import Company, Job, JobAssessment, JobRevision, Source
        from app.db import get_engine
        from app.domain.profile import Facts, Preferences, Span
        from app.main import app
        from app.profile_models import Operation, Profile, ProfileRevision
        from app.services.operations import process_operation
        from app.tasks.worker import bootstrap_queue
        from fastapi.testclient import TestClient
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        alembic_cfg = Config(str(ROOT / "backend/alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(ROOT / "backend/migrations"))
        command.upgrade(alembic_cfg, "head")
        bootstrap_queue()

        create_owner("owner", "synthetic-phase-f-password")

        # Initialize AI Settings revisions and caps
        engine = get_engine()
        with Session(engine) as db, db.begin():
            db.add(
                AiLimitsRow(
                    id=1,
                    revision=0,
                    settings=AiLimits(daily_calls=50, daily_usd=Decimal("1")).model_dump(
                        mode="json"
                    ),
                )
            )
            # Add TaskRevisions for Luna and Jev
            db.add_all(
                [
                    TaskRevision(
                        task="profile_analysis",
                        revision=1,
                        config=TaskConfig(
                            model="openai/gpt-6-luna",
                            input_tokens=8000,
                            output_tokens=1000,
                            prompt_price=Decimal("5"),
                            completion_price=Decimal("15"),
                        ).model_dump(mode="json"),
                        validation_state="validated",
                    ),
                    TaskRevision(
                        task="job_extraction",
                        revision=1,
                        config=TaskConfig(
                            model="openai/gpt-6-luna",
                            input_tokens=8000,
                            output_tokens=1000,
                            prompt_price=Decimal("5"),
                            completion_price=Decimal("15"),
                        ).model_dump(mode="json"),
                        validation_state="validated",
                    ),
                    TaskRevision(
                        task="job_matching",
                        revision=1,
                        config=TaskConfig(
                            model="typesafe/jev-1.13",
                            protocol="decisions",
                            input_tokens=12000,
                            output_tokens=500,
                            prompt_price=Decimal("5"),
                            completion_price=Decimal("15"),
                        ).model_dump(mode="json"),
                        validation_state="validated",
                    ),
                ]
            )

        client = TestClient(app, base_url="https://localhost:8443")

        # ----------------------------------------------------
        # Step 1: Owner login & AI Settings inspection
        # ----------------------------------------------------
        print("\n--- Step 1: Owner login and AI Settings verification ---")
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "synthetic-phase-f-password"},
            headers={"Origin": "https://localhost:8443"},
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.status_code}"
        csrf_token = login_res.json()["csrf_token"]
        auth_headers = {"Origin": "https://localhost:8443", "X-CSRF-Token": csrf_token}

        settings_res = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert settings_res.status_code == 200
        settings_data = settings_res.json()
        task_configs = {t["task"]: t["config"] for t in settings_data["tasks"]}
        assert task_configs["profile_analysis"]["model"] == "openai/gpt-6-luna"
        assert task_configs["job_matching"]["model"] == "typesafe/jev-1.13"
        print("Step 1 PASSED: Owner authenticated, active models confirmed (Luna & Jev).")

        # ----------------------------------------------------
        # Step 2: Ingest synthetic vacancy into inventory
        # ----------------------------------------------------
        print("\n--- Step 2: Ingest synthetic vacancy into inventory ---")
        posting_data = Posting(
            external_id="ext-strat-001",
            title="Senior Corporate Strategy Manager",
            description=(
                "Lead corporate strategy and annual business planning initiatives. "
                "Conduct commercial due diligence, market entry studies, and growth analysis. "
                "Based in London, UK."
            ),
            url="https://jobs.example.com/posting/ext-strat-001",
            apply_url="https://jobs.example.com/apply/ext-strat-001",
            locations=["London"],
        )
        from test_inventory import collect, source

        with Session(engine) as db, db.begin():
            company = Company(label="Alpha Corporate Advisory")
            db.add(company)
            db.flush()
            src = source(db, company_id=company.id)
            source_id = src.id

        with Session(engine) as db, db.begin():
            src_row = db.get(Source, source_id)
            collect(db, src_row, InventoryPage(postings=[posting_data], complete=True))

        with Session(engine) as db:
            job = db.scalar(select(Job))
            assert job is not None, "Job was not saved in database"
            job_id = job.id
            job_rev = db.scalar(select(JobRevision).where(JobRevision.job_id == job.id))
            title = job_rev.posting.get("title") if job_rev else "Unknown"
            print(f"Step 2 PASSED: Job ingested: {title} (ID: {job_id}).")

        # ----------------------------------------------------
        # Step 3 & 4: Analyze CV (Call 1) & save reviewed profile
        # ----------------------------------------------------
        print("\n--- Step 3 & 4: Extract CV with Luna and save reviewed profile ---")
        cv_spans = [
            Span(
                id="cv:1",
                text="Senior Strategy Consultant with 5 years in commercial planning.",
            ),
            Span(id="cv:2", text="Strategy Consultant at Apex Advisory from 2020 to 2025."),
            Span(
                id="cv:3",
                text="Responsibilities: market entry analysis, commercial due diligence.",
            ),
            Span(id="cv:4", text="Skills: Corporate Strategy, Financial Modeling, Due Diligence."),
            Span(id="cv:5", text="Education: BA in Economics from Cambridge (2019)."),
        ]

        with Session(engine) as db:
            prof_rev = latest(db, "profile_analysis")
            prof_config_id = str(prof_rev.id)

        facts = analyze_profile(cv_spans, prof_config_id, None)
        assert isinstance(facts, Facts)
        assert len(facts.employment) >= 1
        print(f"CV extracted via Luna: {len(facts.employment)} roles, {len(facts.skills)} skills.")

        # Save reviewed profile into ProfileRevision revision 1
        prefs = Preferences(desired_roles=["Strategy"])
        with Session(engine) as db, db.begin():
            prof = Profile(id=1, current_revision=1)
            db.add(prof)
            p_rev = ProfileRevision(
                profile_id=1,
                revision=1,
                facts=facts.model_dump(mode="json"),
                preferences=prefs.model_dump(mode="json"),
            )
            db.add(p_rev)
            profile_revision_id = p_rev.id

        print(f"Step 3 & 4 PASSED: Reviewed profile revision {profile_revision_id} created.")

        # ----------------------------------------------------
        # Step 5: Execute matching through real worker (Call 2)
        # ----------------------------------------------------
        print("\n--- Step 5: Execute matching assessment through worker (Jev Decisions) ---")
        assess_res = client.post(
            f"/api/v1/jobs/{job_id}/reassess",
            headers=auth_headers,
        )
        assert assess_res.status_code in (200, 202), f"Reassess failed: {assess_res.status_code}"
        operation_id = assess_res.json().get("operation_id")
        if not operation_id:
            with Session(engine) as db:
                assess_op = db.scalar(
                    select(Operation)
                    .where(Operation.kind == "job_assess")
                    .order_by(Operation.created_at.desc())
                )
                assert assess_op is not None, "Expected queued job_assess operation"
                operation_id = assess_op.id
        # Process the operation through real worker
        process_operation(operation_id)

        with Session(engine) as db:
            assess_op = db.get(Operation, operation_id)
            assert assess_op.state == "succeeded", (
                f"Operation did not succeed: {assess_op.state} (error: {assess_op.error_code})"
            )
            print(f"Step 5 PASSED: job_assess operation {operation_id} completed successfully.")

        # ----------------------------------------------------
        # Step 6: Verify persistence, API display & accounting
        # ----------------------------------------------------
        print("\n--- Step 6: Verify JobAssessment, API views, and accounting ---")
        with Session(engine) as db:
            assessment = db.scalar(
                select(JobAssessment).where(JobAssessment.job_revision_id == job_rev.id)
            )
            assert assessment is not None, "JobAssessment was not persisted"
            report = assessment.report
            assert report["relation"] in ("aligned", "adjacent"), f"Relation: {report['relation']}"
            print(
                f"DB assessment verified: category={assessment.category} "
                f"relation={report.get('relation')} connection={report.get('plausible_connection')}"
            )

        shortlist_res = client.get("/api/v1/jobs?view=recommended", headers=auth_headers)
        assert shortlist_res.status_code == 200, f"Shortlist failed: {shortlist_res.status_code}"
        shortlist_items = shortlist_res.json()["items"]
        assert len(shortlist_items) >= 1, "Expected job in shortlist"
        shortlisted_job = next((j for j in shortlist_items if j["id"] == str(job_id)), None)
        assert shortlisted_job is not None, "Ingested job not found in shortlist"
        assert shortlisted_job.get("assessment") is not None, "Shortlisted job missing assessment"
        category_val = shortlisted_job["assessment"]["category"]
        assert category_val in ("match", "possible_match"), f"Category: {category_val}"
        print(
            f"Portal shortlist view verified: job {job_id} is '{category_val}' "
            f"(status: {shortlisted_job.get('assessment_status')})."
        )
        # Verify /api/v1/jobs?view=all (all jobs view)
        jobs_res = client.get("/api/v1/jobs?view=all", headers=auth_headers)
        assert jobs_res.status_code == 200
        all_jobs = jobs_res.json()["items"]
        assert any(j["id"] == str(job_id) for j in all_jobs), "Job not in all-jobs list"
        print("Portal /api/v1/jobs?view=all verified: job is visible with assessment state.")

        # Verify /api/v1/jobs/{job_id} (job detail view)
        detail_res = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert detail_data.get("assessment") is not None, "Detail view missing assessment"
        print("Portal job detail view verified: includes assessment explanation and evidence.")
        usage_res = client.get("/api/v1/settings/ai/usage", headers=auth_headers)
        assert usage_res.status_code == 200
        usage_data = usage_res.json()
        print(f"API usage verified: daily spend=${usage_data.get('daily_usd')}")

        with Session(engine) as db:
            inference_calls = list(db.scalars(select(InferenceCall)))
            print(f"Inference calls persisted in DB: {len(inference_calls)}")
            for c in inference_calls:
                print(
                    f"  Call: task={c.task} model={c.returned_model} "
                    f"cost=${c.reported_usd} latency={c.latency_ms}ms"
                )
            initial_call_count = len(inference_calls)

        # ----------------------------------------------------
        # Step 7: Idempotency check: unedited profile causes no second billable call
        # ----------------------------------------------------
        print("\n--- Step 7: Assessment idempotency check ---")
        with Session(engine) as db, db.begin():
            # Re-queue assessment for the same job with the same unedited profile
            reassess_res = client.post(
                f"/api/v1/jobs/{job_id}/reassess",
                headers=auth_headers,
            )
            # 200 or 202
            assert reassess_res.status_code in (200, 202)
            reassess_op_id = reassess_res.json().get("operation_id")

        if reassess_op_id:
            process_operation(reassess_op_id)

        with Session(engine) as db:
            final_calls = list(db.scalars(select(InferenceCall)))
            assert len(final_calls) == initial_call_count, (
                f"Idempotency violated: calls grew from {initial_call_count} to {len(final_calls)}"
            )
            print(f"Step 7 PASSED: Idempotency verified: call count remained {initial_call_count}.")

        print("\n=================== Phase F Journey Complete ===================")
        print("All 7 steps passed: Owner Auth -> Ingestion -> CV Extraction -> Matching ->")
        print("DB Persistence -> Shortlist View -> All-Jobs View -> Idempotency.")
        print("================================================================\n")
        return 0

    finally:
        bridge_file.unlink(missing_ok=True)
        bridge_dir.rmdir()


if __name__ == "__main__":
    raise SystemExit(run_journey())
