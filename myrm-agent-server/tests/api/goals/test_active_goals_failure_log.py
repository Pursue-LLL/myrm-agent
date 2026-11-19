"""One session's unreadable goal does not empty the active-goals listing, and the failure is logged.

[INPUT]
- app.api.goals.router (POS: Goal HTTP endpoints for the frontend)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: Goal registry, one provider per session)

[OUTPUT]
- A case proving a provider that raises is left out with a router WARNING that names its session.
- A case proving a session whose stored index is unreadable is left out while GoalStorage names it once.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent.goals.goal_registry import GoalRegistry

_ROUTER_LOGGER = "app.api.goals.router"
_STORAGE_LOGGER = "myrm_agent_harness.agent.goals.storage"
_FAILURE = "provider failed"


@pytest.fixture
def sessions() -> tuple[str, str]:
    """A session whose goal reads fine and one that fails."""
    token = uuid.uuid4().hex
    return f"active-goals-ok-{token}", f"active-goals-failing-{token}"


def _list_active_goals(client: TestClient) -> dict[str, str]:
    """Goal id per session as GET /goals/active reports it."""
    response = client.get("/api/v1/goals/active")
    assert response.status_code == 200
    return {item["session_id"]: item["goal_id"] for item in response.json()["goals"]}


def _warnings(caplog: pytest.LogCaptureFixture, logger_name: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == logger_name and r.levelno >= logging.WARNING]


@pytest.mark.asyncio
async def test_a_provider_that_raises_is_warned_about_and_the_other_goals_are_still_listed(
    client: TestClient, sessions: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    healthy, failing = sessions
    goal = await GoalRegistry.register(healthy).create_goal(healthy, "Ship the quarterly report")
    failing_provider = GoalRegistry.register(failing)

    with (
        patch.object(failing_provider, "get_latest_goal", new=AsyncMock(side_effect=RuntimeError(_FAILURE))),
        caplog.at_level(logging.WARNING, logger=_ROUTER_LOGGER),
    ):
        listed = _list_active_goals(client)

    assert listed.get(healthy) == goal.goal_id
    assert failing not in listed
    assert f"Failed to get goal for session {failing}: {_FAILURE}" in _warnings(caplog, _ROUTER_LOGGER)


@pytest.mark.asyncio
async def test_an_unreadable_index_is_named_once_and_the_other_goals_are_still_listed(
    client: TestClient, sessions: tuple[str, str], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    healthy, damaged = sessions
    goal = await GoalRegistry.register(healthy).create_goal(healthy, "Ship the quarterly report")
    GoalRegistry.register(damaged)
    (tmp_path / "goals_latest" / damaged).mkdir(parents=True)  # a directory where the index file belongs

    with caplog.at_level(logging.WARNING, logger=_STORAGE_LOGGER):
        listings = [_list_active_goals(client) for _ in range(2)]

    for listed in listings:
        assert listed.get(healthy) == goal.goal_id
        assert damaged not in listed
    named = _warnings(caplog, _STORAGE_LOGGER)
    assert len(named) == 1
    assert f"Goal latest index for session {damaged!r}" in named[0]
