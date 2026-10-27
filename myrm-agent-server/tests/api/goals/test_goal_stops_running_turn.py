"""Pausing or cancelling a goal over HTTP stops the turn the goal was working on."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken

from app.services.agent.gateway import AgentGateway
from app.services.agent.goals.goal_registry import GoalRegistry

_MESSAGE_ID = "message-in-flight"


@pytest.fixture
def session_id() -> Iterator[str]:
    sid = f"goal-stop-{uuid.uuid4().hex[:8]}"
    yield sid
    GoalRegistry.unregister(sid)


@pytest.fixture
def running_turn() -> Iterator[tuple[MagicMock, CancellationToken]]:
    """A turn in flight: the gateway has a live session and the registry holds the message's token."""
    gateway = MagicMock(spec=AgentGateway)
    gateway.get_active_message_id.return_value = _MESSAGE_ID
    gateway.interrupt_session.return_value = True
    token = CancellationToken(_MESSAGE_ID)
    CancellationRegistry.register(token)
    with patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=gateway):
        yield gateway, token
    CancellationRegistry.unregister(_MESSAGE_ID)


async def _goal_in_status(sid: str, status: GoalStatus) -> None:
    provider = GoalRegistry.get_or_create_provider(sid)
    goal = await provider.create_goal(sid, "Ship the report")
    if status is not GoalStatus.ACTIVE:
        await provider.update_status(goal.goal_id, status)


@pytest.mark.parametrize(("action", "new_status"), [("pause", "paused"), ("cancel", "cancelled")])
async def test_pause_and_cancel_stop_the_turn_the_goal_is_working_on(
    client: TestClient,
    session_id: str,
    running_turn: tuple[MagicMock, CancellationToken],
    action: str,
    new_status: str,
) -> None:
    gateway, token = running_turn
    await _goal_in_status(session_id, GoalStatus.ACTIVE)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": action})

    assert response.status_code == 200
    assert response.json()["new_status"] == new_status
    gateway.interrupt_session.assert_called_once_with(session_id)
    assert token.is_cancelled


@pytest.mark.parametrize("status", [GoalStatus.BUDGET_LIMITED, GoalStatus.NEEDS_HUMAN_REVIEW, GoalStatus.PAUSED, GoalStatus.WAIT])
async def test_cancelling_a_goal_that_is_not_working_leaves_the_session_turn_alone(
    client: TestClient,
    session_id: str,
    running_turn: tuple[MagicMock, CancellationToken],
    status: GoalStatus,
) -> None:
    gateway, token = running_turn
    await _goal_in_status(session_id, status)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "cancel"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "cancelled"
    gateway.interrupt_session.assert_not_called()
    assert not token.is_cancelled


async def test_pausing_a_waiting_goal_leaves_the_session_turn_alone(
    client: TestClient, session_id: str, running_turn: tuple[MagicMock, CancellationToken]
) -> None:
    gateway, token = running_turn
    await _goal_in_status(session_id, GoalStatus.WAIT)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "paused"
    gateway.interrupt_session.assert_not_called()
    assert not token.is_cancelled


async def test_cancel_succeeds_when_no_turn_is_running(client: TestClient, session_id: str) -> None:
    gateway = MagicMock(spec=AgentGateway)
    gateway.get_active_message_id.return_value = None
    gateway.interrupt_session.return_value = False
    await _goal_in_status(session_id, GoalStatus.ACTIVE)

    with patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=gateway):
        response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "cancel"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "cancelled"
