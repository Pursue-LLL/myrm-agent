"""Goal objective and constraint text is read by the agent on every iteration: a secret in it is refused before it is stored."""

import uuid
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.risk.refusal import RISK_HELD_CODE
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

_DETECTION = "app.services.risk.detection.get_detection_service"


@pytest.fixture
async def session_id() -> AsyncIterator[str]:
    session = f"risk_gate_{uuid.uuid4().hex}"
    provider = GoalRegistry.get_or_create_provider(session)
    await provider.create_goal(session, "Original objective")
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        yield session
    GoalRegistry.unregister(session)


async def test_objective_with_a_secret_is_refused_and_unchanged(client: TestClient, session_id: str) -> None:
    response = client.patch(f"/api/v1/goals/{session_id}/objective", json={"objective": f"deploy with {SECRET}"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == RISK_HELD_CODE
    goal = await GoalRegistry.get_provider(session_id).get_latest_goal(session_id)
    assert goal.objective == "Original objective"


async def test_clean_objective_is_stored(client: TestClient, session_id: str) -> None:
    response = client.patch(f"/api/v1/goals/{session_id}/objective", json={"objective": "ship the release notes"})

    assert response.status_code == 200
    assert response.json()["goal"]["objective"] == "ship the release notes"


async def test_constraint_with_a_secret_is_refused_and_unchanged(client: TestClient, session_id: str) -> None:
    response = client.put(f"/api/v1/goals/{session_id}/constraints", json={"constraints": ["be brief", f"key {SECRET}"]})

    assert response.status_code == 400
    assert response.json()["detail"]["rules"][0]["rule_id"] == "r-apikey"
    goal = await GoalRegistry.get_provider(session_id).get_latest_goal(session_id)
    assert goal.constraints == []


async def test_clean_constraints_are_stored(client: TestClient, session_id: str) -> None:
    response = client.put(f"/api/v1/goals/{session_id}/constraints", json={"constraints": ["be brief"]})

    assert response.status_code == 200
    assert response.json()["constraints"] == ["be brief"]
