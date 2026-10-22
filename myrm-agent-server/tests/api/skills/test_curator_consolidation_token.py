"""Consolidation execute only runs the plan the user previewed: the token comes from preview, works once, and is tied to that plan."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.curator.consolidation.types import ConsolidationPlan

_PREVIEW_URL = "/api/v1/skills/curator/consolidation/preview"
_EXECUTE_URL = "/api/v1/skills/curator/consolidation/execute"
_EXECUTION_RESULT = {
    "success_count": 1,
    "failure_count": 0,
    "total_archived": 2,
    "total_created": 1,
    "net_reduction": 1,
    "summary": "Consolidated 2 skills into 1 umbrella.",
}


def _issue_token(client: TestClient, previewed_plan: ConsolidationPlan) -> str:
    with patch(
        "app.core.skills.curator.consolidation.run_consolidation_preview",
        AsyncMock(return_value=previewed_plan),
    ):
        response = client.post(_PREVIEW_URL)
    assert response.status_code == 200
    return str(response.json()["plan_token"])


def _execute(client: TestClient, token: str, *, current_plan: ConsolidationPlan) -> tuple[int, AsyncMock]:
    """Post an execute request (it previews the plan again itself); return its status and the patched execution."""
    execution = AsyncMock(return_value=_EXECUTION_RESULT)
    with (
        patch(
            "app.core.skills.curator.consolidation.run_consolidation_preview",
            AsyncMock(return_value=current_plan),
        ),
        patch("app.core.skills.curator.consolidation.run_consolidation_execute", execution),
    ):
        response = client.post(_EXECUTE_URL, json={"plan_token": token})
    return response.status_code, execution


def test_execute_runs_for_the_token_the_preview_issued(client: TestClient) -> None:
    plan = ConsolidationPlan()
    token = _issue_token(client, plan)

    status, execution = _execute(client, token, current_plan=plan)

    assert status == 200
    execution.assert_awaited_once()


def test_execute_rejects_a_token_the_preview_never_issued(client: TestClient) -> None:
    status, execution = _execute(client, "forged-token", current_plan=ConsolidationPlan())

    assert status == 409
    execution.assert_not_awaited()


def test_a_token_executes_only_once(client: TestClient) -> None:
    plan = ConsolidationPlan()
    token = _issue_token(client, plan)
    assert _execute(client, token, current_plan=plan)[0] == 200

    status, execution = _execute(client, token, current_plan=plan)

    assert status == 409
    execution.assert_not_awaited()


def test_execute_rejects_a_token_when_the_plan_changed_after_the_preview(client: TestClient) -> None:
    token = _issue_token(client, ConsolidationPlan(preview_summary="the plan the user saw"))

    status, execution = _execute(client, token, current_plan=ConsolidationPlan(preview_summary="a different plan"))

    assert status == 409
    execution.assert_not_awaited()
