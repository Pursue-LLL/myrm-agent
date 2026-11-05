"""Consolidation execute applies the plan the user previewed: the token comes from preview, works once, and names that plan."""

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


def _merge_plan(target: str = "report_skill") -> ConsolidationPlan:
    merge = ConsolidationAction(
        action_type=ConsolidationActionType.MERGE,
        target_skill=target,
        source_skills=("report_a", "report_b"),
        reasoning="same job",
    )
    return ConsolidationPlan(actions=[merge], total_skills_affected=2, estimated_reduction=1)


def _preview(client: TestClient, previewed_plan: ConsolidationPlan) -> str:
    with patch(
        "app.core.skills.curator.consolidation.run_consolidation_preview",
        AsyncMock(return_value=previewed_plan),
    ):
        response = client.post(_PREVIEW_URL)
    assert response.status_code == 200
    return str(response.json()["plan_token"])


def _execute(client: TestClient, token: str) -> tuple[int, AsyncMock, AsyncMock]:
    """Post an execute request; return its status, the patched execution and the patched preview."""
    execution = AsyncMock(return_value=_EXECUTION_RESULT)
    preview = AsyncMock(return_value=ConsolidationPlan())
    with (
        patch("app.core.skills.curator.consolidation.run_consolidation_execute", execution),
        patch("app.core.skills.curator.consolidation.run_consolidation_preview", preview),
    ):
        response = client.post(_EXECUTE_URL, json={"plan_token": token})
    return response.status_code, execution, preview


def test_execute_applies_the_plan_the_preview_returned(client: TestClient) -> None:
    plan = _merge_plan()
    token = _preview(client, plan)

    status, execution, preview = _execute(client, token)

    assert status == 200
    execution.assert_awaited_once_with(plan)
    preview.assert_not_awaited()


def test_execute_rejects_a_token_the_preview_never_issued(client: TestClient) -> None:
    status, execution, _ = _execute(client, "forged-token")

    assert status == 409
    execution.assert_not_awaited()


def test_a_token_executes_only_once(client: TestClient) -> None:
    token = _preview(client, _merge_plan())
    assert _execute(client, token)[0] == 200

    status, execution, _ = _execute(client, token)

    assert status == 409
    execution.assert_not_awaited()


def test_every_preview_keeps_its_own_plan(client: TestClient) -> None:
    """A second preview (another tab, a re-click) does not replace the plan the first token names."""
    first, second = _merge_plan("report_skill"), _merge_plan("invoice_skill")
    first_token = _preview(client, first)
    _preview(client, second)

    status, execution, _ = _execute(client, first_token)

    assert status == 200
    execution.assert_awaited_once_with(first)


def test_execute_rejects_an_expired_token(client: TestClient) -> None:
    with patch("app.core.skills.curator.consolidation_plan_store._TTL_SECONDS", -1):
        token = _preview(client, _merge_plan())

    status, execution, _ = _execute(client, token)

    assert status == 409
    execution.assert_not_awaited()
