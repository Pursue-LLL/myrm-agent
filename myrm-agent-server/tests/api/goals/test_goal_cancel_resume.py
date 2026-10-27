"""Goal cancel and resume over HTTP: cancel reaches every open goal, resume puts the goal back to work."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.goals.protocols import GoalProvider
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture
def session_id() -> Iterator[str]:
    sid = f"goal-controls-{uuid.uuid4().hex[:8]}"
    yield sid
    GoalRegistry.unregister(sid)


async def _goal_in_status(sid: str, status: GoalStatus) -> tuple[GoalProvider, str]:
    provider = GoalRegistry.get_or_create_provider(sid)
    goal = await provider.create_goal(sid, "Ship the report")
    if status is not GoalStatus.ACTIVE:
        await provider.update_status(goal.goal_id, status)
    return provider, goal.goal_id


@pytest.mark.parametrize(
    "status",
    [
        GoalStatus.ACTIVE,
        GoalStatus.PAUSED,
        GoalStatus.BUDGET_LIMITED,
        GoalStatus.NEEDS_HUMAN_REVIEW,
        GoalStatus.WAIT,
        GoalStatus.PENDING_APPROVAL,
    ],
)
async def test_cancel_reaches_every_open_goal(client: TestClient, session_id: str, status: GoalStatus) -> None:
    _, goal_id = await _goal_in_status(session_id, status)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "cancel"})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "goal_id": goal_id, "new_status": "cancelled"}


async def test_cancel_with_only_a_finished_goal_is_not_found(client: TestClient, session_id: str) -> None:
    await _goal_in_status(session_id, GoalStatus.COMPLETE)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "cancel"})

    assert response.status_code == 404


@pytest.mark.parametrize("status", [GoalStatus.PAUSED, GoalStatus.BUDGET_LIMITED])
async def test_resume_puts_the_goal_back_to_work(
    client: TestClient, goal_stream_trigger: AsyncMock, session_id: str, status: GoalStatus
) -> None:
    _, goal_id = await _goal_in_status(session_id, status)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_awaited_once()
    started_session, started_goal, _provider = goal_stream_trigger.await_args.args
    assert started_session == session_id
    assert started_goal.goal_id == goal_id
    assert started_goal.status is GoalStatus.ACTIVE


@pytest.mark.parametrize(
    "gateway",
    [
        SimpleNamespace(is_draining=False, is_session_active=lambda _sid: True),
        SimpleNamespace(is_draining=True, is_session_active=lambda _sid: False),
    ],
    ids=["session-busy", "app-draining"],
)
async def test_resume_does_not_start_a_second_turn_when_the_session_cannot_take_one(
    client: TestClient, goal_stream_trigger: AsyncMock, session_id: str, gateway: SimpleNamespace
) -> None:
    await _goal_in_status(session_id, GoalStatus.PAUSED)

    with patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=gateway):
        response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_not_awaited()


async def test_resume_succeeds_even_when_the_turn_could_not_be_started(
    client: TestClient, goal_stream_trigger: AsyncMock, session_id: str
) -> None:
    await _goal_in_status(session_id, GoalStatus.PAUSED)
    goal_stream_trigger.return_value = False

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_awaited_once()


async def test_rejecting_a_review_leaves_the_next_message_to_the_client(
    client: TestClient, goal_stream_trigger: AsyncMock, session_id: str
) -> None:
    await _goal_in_status(session_id, GoalStatus.NEEDS_HUMAN_REVIEW)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "reject"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_not_awaited()
