"""Kanban task skill-id validation tests.

Verifies that the user-facing create/update API rejects skill ids that are
not part of the discoverable skill set, so a mistyped task skill is never
silently dropped at worker startup (harness load_skills logs + continues).
Decompose and pipeline instantiation call the service layer directly and are
intentionally not covered here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.api.kanban.router import router as kanban_router
from app.core.skills.models import Skill
from app.core.skills.store.service import skills_service
from app.services.kanban import KanbanService


def _skill(skill_id: str) -> Skill:
    return Skill(
        id=skill_id,
        type=SkillType.PREBUILT,
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
    """Bypass agent_id validation for tests that don't test it explicitly."""
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture(autouse=True)
def _known_skills() -> None:
    """Default discoverable skill set: {"web-search", "content-writer"}."""
    with patch.object(
        skills_service,
        "list_skills",
        new_callable=AsyncMock,
        return_value=[_skill("web-search"), _skill("content-writer")],
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


class TestTaskSkillValidation:
    def test_create_rejects_unknown_skill_id(self, client: TestClient) -> None:
        board_id = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Task", "extra_skill_ids": ["web-search", "typo-skill"]},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "typo-skill" in detail
        assert "web-search" in detail

    def test_create_accepts_known_skill_ids(self, client: TestClient) -> None:
        board_id = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Task", "extra_skill_ids": ["web-search", "content-writer"]},
        )
        assert resp.status_code == 201
        assert resp.json()["extra_skill_ids"] == ["web-search", "content-writer"]

    def test_create_without_skills_is_allowed(self, client: TestClient) -> None:
        board_id = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Task"},
        )
        assert resp.status_code == 201

    def test_update_rejects_unknown_skill_id(self, client: TestClient) -> None:
        board_id = _create_board(client)
        created = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Task"},
        )
        task_id = created.json()["task_id"]
        resp = client.patch(
            f"/api/v1/kanban/tasks/{task_id}",
            json={"extra_skill_ids": ["nope-skill"]},
        )
        assert resp.status_code == 400
        assert "nope-skill" in resp.json()["detail"]

    def test_duplicate_unknown_ids_are_reported_once(self, client: TestClient) -> None:
        board_id = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Task", "extra_skill_ids": ["typo-skill", "typo-skill"]},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail.count("typo-skill") == 1

    def test_update_accepts_known_skill_id(self, client: TestClient) -> None:
        board_id = _create_board(client)
        created = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Task"},
        )
        task_id = created.json()["task_id"]
        resp = client.patch(
            f"/api/v1/kanban/tasks/{task_id}",
            json={"extra_skill_ids": ["content-writer"]},
        )
        assert resp.status_code == 200
        assert resp.json()["extra_skill_ids"] == ["content-writer"]
