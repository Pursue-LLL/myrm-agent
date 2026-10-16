"""Goal text is read by the agent on every iteration: a secret in the objective, a constraint, a subgoal or the draft request is refused before it is stored or sent to a model."""

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.api.dependencies import get_optional_llm_for_user
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.risk.refusal import RISK_HELD_CODE
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

_DETECTION = "app.services.risk.detection.get_detection_service"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A bare app that mounts only the goals router, backed by throwaway local storage."""
    from app.api.goals.router import router as goals_router

    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")
    app.dependency_overrides[get_optional_llm_for_user] = lambda: MagicMock()

    with (
        patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))),
        patch("app.api.goals.router.get_features") as features,
    ):
        features.return_value.enabled.return_value = True
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(autouse=True)
def _risk_rules() -> Iterator[None]:
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        yield


@pytest.fixture
async def session_id() -> AsyncIterator[str]:
    session = f"risk_gate_{uuid.uuid4().hex}"
    provider = GoalRegistry.get_or_create_provider(session)
    await provider.create_goal(session, "Original objective")
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


async def test_subgoal_with_a_secret_is_refused_and_not_added(client: TestClient, session_id: str) -> None:
    response = client.post(f"/api/v1/goals/{session_id}/subgoals", json={"text": f"call the API with {SECRET}"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == RISK_HELD_CODE
    goal = await GoalRegistry.get_provider(session_id).get_latest_goal(session_id)
    assert goal.subgoals == []


async def test_clean_subgoal_is_added(client: TestClient, session_id: str) -> None:
    response = client.post(f"/api/v1/goals/{session_id}/subgoals", json={"text": "collect the 2026 rows"})

    assert response.status_code == 200
    goal = await GoalRegistry.get_provider(session_id).get_latest_goal(session_id)
    assert len(goal.subgoals) == 1


@pytest.fixture
async def reviewed_session(session_id: str) -> str:
    """A session whose goal failed its review and waits for the user to reject or approve it."""
    provider = GoalRegistry.get_provider(session_id)
    goal = await provider.get_latest_goal(session_id)
    await provider.update_status(goal.goal_id, GoalStatus.NEEDS_HUMAN_REVIEW)
    return session_id


async def test_review_feedback_with_a_secret_keeps_the_goal_in_review(client: TestClient, reviewed_session: str) -> None:
    response = client.post(f"/api/v1/goals/{reviewed_session}/status", json={"action": "reject", "note": f"retry with {SECRET}"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == RISK_HELD_CODE
    goal = await GoalRegistry.get_provider(reviewed_session).get_latest_goal(reviewed_session)
    assert goal.status is GoalStatus.NEEDS_HUMAN_REVIEW


@pytest.mark.parametrize("body", [{"action": "reject", "note": "use the staging data"}, {"action": "reject"}])
async def test_review_feedback_without_a_secret_sends_the_goal_back_to_work(
    client: TestClient, reviewed_session: str, body: dict[str, str]
) -> None:
    response = client.post(f"/api/v1/goals/{reviewed_session}/status", json=body)

    assert response.status_code == 200
    goal = await GoalRegistry.get_provider(reviewed_session).get_latest_goal(reviewed_session)
    assert goal.status is GoalStatus.ACTIVE


def test_draft_request_with_a_secret_never_reaches_the_model(client: TestClient) -> None:
    drafted = AsyncMock(return_value={"constraints": [], "acceptance_criteria": [], "ui_summary": ""})

    with patch("app.services.agent.goals.goal_draft.draft_goal_spec", drafted):
        response = client.post("/api/v1/goals/draft", json={"objective": f"deploy with {SECRET}"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == RISK_HELD_CODE
    drafted.assert_not_awaited()


def test_clean_draft_request_reaches_the_model(client: TestClient) -> None:
    drafted = AsyncMock(return_value={"constraints": ["be brief"], "acceptance_criteria": [], "ui_summary": "ok"})

    with patch("app.services.agent.goals.goal_draft.draft_goal_spec", drafted):
        response = client.post("/api/v1/goals/draft", json={"objective": "ship the release notes"})

    assert response.status_code == 200
    drafted.assert_awaited_once()
