"""One session's unreadable goal does not empty the active-goals listing, and the failure is logged.

[INPUT]
- app.api.goals.router (POS: Goal HTTP endpoints for the frontend)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: Goal registry, one provider per session)

[OUTPUT]
- A case proving a session whose goal cannot be read is left out with a WARNING that names it.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent.goals.goal_registry import GoalRegistry

_ROUTER_LOGGER = "app.api.goals.router"
_LOCKED = "database is locked"


@pytest.fixture
def sessions() -> Iterator[tuple[str, str]]:
    """A session whose goal reads fine and one whose storage is busy; both leave the process-wide registry after."""
    token = uuid.uuid4().hex
    healthy, busy = f"active-goals-ok-{token}", f"active-goals-busy-{token}"
    yield healthy, busy
    GoalRegistry.unregister(healthy)
    GoalRegistry.unregister(busy)


@pytest.mark.asyncio
async def test_an_unreadable_session_is_warned_about_and_the_other_goals_are_still_listed(
    client: TestClient, sessions: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    healthy, busy = sessions
    goal = await GoalRegistry.get_or_create_provider(healthy).create_goal(healthy, "Ship the quarterly report")
    busy_provider = GoalRegistry.get_or_create_provider(busy)

    with (
        patch.object(busy_provider, "get_latest_goal", new=AsyncMock(side_effect=sqlite3.OperationalError(_LOCKED))),
        caplog.at_level(logging.WARNING, logger=_ROUTER_LOGGER),
    ):
        response = client.get("/api/v1/goals/active")

    assert response.status_code == 200
    listed = {item["session_id"]: item["goal_id"] for item in response.json()["goals"]}
    assert listed.get(healthy) == goal.goal_id
    assert busy not in listed
    warnings = [r.getMessage() for r in caplog.records if r.name == _ROUTER_LOGGER and r.levelno >= logging.WARNING]
    assert f"Failed to get goal for session {busy}: {_LOCKED}" in warnings
