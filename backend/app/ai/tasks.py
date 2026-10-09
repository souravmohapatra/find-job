from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.ai import provider
from app.ai.configuration import set_validation
from app.ai.contracts import TaskKey
from app.ai.decisions import (
    ChoiceAnswer,
    DecisionsQuestion,
    DecisionsTask,
    NoulAnswer,
    ScoreAnswer,
)
from app.ai.models import InferenceCall
from app.ai.provider import http_failure, infer, money, stored_protocol
from app.config import get_settings
from app.db import get_engine
from app.profile_models import now
from app.services.operations import OperationError


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


def validate_task(task: TaskKey, config_id: UUID, operation_id: UUID) -> None:
    if get_settings().integration_mode == "mock":
        set_validation(config_id, "mock_only")
        return
    if stored_protocol(config_id, task) == "decisions":
        infer(
            task,
            config_id,
            operation_id,
            "",
            {},
            Probe,
            prompt_version="probe-v1",
            schema_version="probe-v1",
            validation_probe=True,
            decisions=DecisionsTask(
                state={"test": "synthetic"},
                questions={
                    "probe": DecisionsQuestion(
                        type="choice",
                        instructions=('Synthetic connectivity probe. Confirm by selecting "ok".'),
                        criteria={"ok": "Always select this.", "error": "Never select this."},
                    )
                },
                interpret=_probe_answer,
            ),
        )
        return
    infer(
        task,
        config_id,
        operation_id,
        'Return {"status":"ok"}. This is a synthetic connectivity and structured-output check.',
        {"test": "synthetic"},
        Probe,
        prompt_version="probe-v1",
        schema_version="probe-v1",
        validation_probe=True,
    )


def _probe_answer(answers: "dict[str, ChoiceAnswer | NoulAnswer | ScoreAnswer]") -> "Probe":
    answer = answers["probe"]
    assert isinstance(answer, ChoiceAnswer)
    if answer.choice != "ok":
        raise ValueError("probe answer must be ok")
    return Probe(status="ok")


def reconcile_call(call_id: UUID) -> None:
    with Session(get_engine()) as db:
        row = db.get(InferenceCall, call_id)
        if row is None or row.state != "unknown" or not row.generation_id:
            return
        generation = row.generation_id
    with provider.client() as http:
        try:
            response = http.get("generation", params={"id": generation})
        except httpx.HTTPError as error:
            raise OperationError(
                "ai_billing_unavailable",
                "Billing lookup is temporarily unavailable; the reservation remains held.",
                retryable=True,
            ) from error
        if response.status_code == 404:
            raise OperationError(
                "ai_cost_pending",
                "Provider billing metadata is not available yet; the reservation remains held.",
                retryable=True,
                retry_after=60,
            )
        if response.status_code != 200:
            raise http_failure(response)
        try:
            data = response.json()["data"]
            cost = money(data.get("total_cost"))
            if data.get("id") != generation or cost is None:
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise OperationError(
                "ai_cost_unknown",
                "The provider has not supplied verifiable billing metadata yet.",
                blocked=True,
            ) from error
    with Session(get_engine()) as db, db.begin():
        row = db.get(InferenceCall, call_id, with_for_update=True)
        if row and row.state == "unknown":
            row.reported_usd = cost
            row.cost_source = "provider"
            row.accounted_at = now()
            settings = get_settings()
            if settings.integration_mode == "live":
                from pathlib import Path

                from app.ai.run_ledger import RunLedger

                # Release the cumulative hold now that provider billing is confirmed.
                RunLedger(Path(settings.live_ledger_path)).settle(str(call_id), cost)
            row.state = "reconciled"
