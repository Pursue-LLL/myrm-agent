"""Consolidation execute only runs the plan the user previewed: the token comes from preview, works once, and is tied to that plan."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationAction,
    ConsolidationActionType,
    ConsolidationPlan,
)

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


def _merge_plan(target: str = "report_skill", *, failed_clusters: int = 0) -> ConsolidationPlan:
    merge = ConsolidationAction(
        action_type=ConsolidationActionType.MERGE,
        target_skill=target,
        source_skills=("report_a", "report_b"),
        reasoning="same job",
    )
    return ConsolidationPlan(actions=[merge], total_skills_affected=2, estimated_reduction=1, failed_clusters=failed_clusters)


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
    token = _issue_token(client, _merge_plan("report_skill"))

    status, execution = _execute(client, token, current_plan=_merge_plan("invoice_skill"))

    assert status == 409
    execution.assert_not_awaited()


def test_execute_accepts_a_plan_that_differs_only_in_how_many_groups_could_not_be_evaluated(client: TestClient) -> None:
    """The token binds the plan the user saw; a transient judge failure is not part of that plan."""
    token = _issue_token(client, _merge_plan(failed_clusters=1))

    status, execution = _execute(client, token, current_plan=_merge_plan(failed_clusters=0))

    assert status == 200
    execution.assert_awaited_once()
