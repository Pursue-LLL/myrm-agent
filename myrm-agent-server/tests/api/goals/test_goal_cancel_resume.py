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
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken, CancelReason

from app.services.agent.goals import goal_controls
from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture
def session_id() -> Iterator[str]:
    sid = f"goal-controls-{uuid.uuid4().hex[:8]}"
    yield sid
    GoalRegistry.unregister(sid)


@pytest.fixture
def stopping_message_id() -> Iterator[str]:
    """The message id of a running turn that was told to stop."""
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    token = CancellationToken(request_id=message_id)
    CancellationRegistry.register(token)
    token.cancel(CancelReason.USER_CANCELLED)
    yield message_id
    CancellationRegistry.unregister(message_id)


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
    assert goal_stream_trigger.await_args is not None
    started_session, started_goal, _provider = goal_stream_trigger.await_args.args
    assert started_session == session_id
    assert started_goal.goal_id == goal_id
    assert started_goal.status is GoalStatus.ACTIVE


@pytest.mark.parametrize(
    "gateway",
    [
        SimpleNamespace(is_draining=False, is_session_active=lambda _sid: True, get_active_message_id=lambda _sid: None),
        SimpleNamespace(is_draining=True, is_session_active=lambda _sid: False, get_active_message_id=lambda _sid: None),
    ],
    ids=["session-busy", "app-draining"],
)
async def test_resume_does_not_start_a_second_turn_when_the_session_cannot_take_one(
    client: TestClient, goal_stream_trigger: AsyncMock, session_id: str, gateway: SimpleNamespace
) -> None:
    await _goal_in_status(session_id, GoalStatus.PAUSED)

    with (
        patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=gateway),
        patch.object(goal_controls, "_STOP_WAIT_SECONDS", 0.05),
    ):
        response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_not_awaited()


async def test_resume_waits_for_the_stopped_turn_before_starting_the_next(
    client: TestClient, goal_stream_trigger: AsyncMock, session_id: str, stopping_message_id: str
) -> None:
    await _goal_in_status(session_id, GoalStatus.PAUSED)
    polls = iter([stopping_message_id, stopping_message_id])
    gateway = SimpleNamespace(
        is_draining=False,
        is_session_active=lambda _sid: False,
        get_active_message_id=lambda _sid: next(polls, None),
    )

    with (
        patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=gateway),
        patch.object(goal_controls, "_STOP_POLL_SECONDS", 0.001),
    ):
        response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_awaited_once()


async def test_resume_is_refused_while_the_stopped_turn_is_still_stopping(
    client: TestClient, goal_stream_trigger: AsyncMock, session_id: str, stopping_message_id: str
) -> None:
    provider, goal_id = await _goal_in_status(session_id, GoalStatus.PAUSED)
    gateway = SimpleNamespace(
        is_draining=False,
        is_session_active=lambda _sid: True,
        get_active_message_id=lambda _sid: stopping_message_id,
    )

    with (
        patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=gateway),
        patch.object(goal_controls, "_STOP_POLL_SECONDS", 0.001),
        patch.object(goal_controls, "_STOP_WAIT_SECONDS", 0.05),
    ):
        response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})

    assert response.status_code == 409
    goal = await provider.get_goal(goal_id)
    assert goal is not None
    assert goal.status is GoalStatus.PAUSED
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
