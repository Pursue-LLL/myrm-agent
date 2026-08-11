"""Kanban task skill validation against the real skill aggregation pipeline.

Integration-level: exercises create/update → ``validate_extra_skill_ids`` →
``skills_service.list_skills`` with its real PREBUILT/LOCAL/WORKSPACE merge.
Only the local skill data source is injected at the provider layer (the test
environment has an empty skill store); the aggregation, dedup, error detail,
and HTTP 400 mapping all run for real.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.api.kanban.router import router as kanban_router
from app.core.skills.models import Skill
from app.services.kanban import KanbanService


def _skill(skill_id: str) -> Skill:
    return Skill(
        id=skill_id,
        type=SkillType.LOCAL,
        name=skill_id.replace("-", " ").title(),
        description="",
        storage_path="",
    )


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure each test gets a fresh KanbanService singleton."""
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    """Bypass agent_id validation; not part of the skill-validation chain."""
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _create_board(client: TestClient) -> str:
    resp = client.post("/api/v1/kanban/boards", json={"name": "Skills Board"})
    assert resp.status_code == 201
    return resp.json()["board_id"]


class TestTaskSkillValidationRealStore:
    """Real aggregation chain: ``list_skills`` itself is never mocked."""

    def test_unknown_id_rejected_when_real_store_has_no_skills(self, client: TestClient) -> None:
        """The real (empty) store yields zero skills, so any id is unknown → 400."""
        board_id = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Task", "extra_skill_ids": [f"ghost-{uuid.uuid4().hex[:8]}"]},
        )
        assert resp.status_code == 400
        assert "Unknown skill id" in resp.json()["detail"]

    def test_injected_local_skill_accepted_through_real_aggregation(self, client: TestClient) -> None:
        """Inject one local skill at the provider layer; the list_skills merge
        (PREBUILT+LOCAL+WORKSPACE), dedup and 400 mapping run unmocked."""
        board_id = _create_board(client)
        with patch(
            "app.core.skills.store.reader.list_local_skills",
            new_callable=AsyncMock,
            return_value=[_skill("local::web-search")],
        ):
            resp = client.post(
                f"/api/v1/kanban/boards/{board_id}/tasks",
                json={"title": "Task", "extra_skill_ids": ["local::web-search"]},
            )
        assert resp.status_code == 201
        assert resp.json()["extra_skill_ids"] == ["local::web-search"]
