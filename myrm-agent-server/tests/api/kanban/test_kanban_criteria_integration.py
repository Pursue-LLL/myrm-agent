"""Kanban completion_criteria API integration tests.

Full-stack tests (HTTP → service → SqlAlchemy → DB → response) validating
that completion_criteria of all supported formats round-trip correctly
through the REST API without mocking the persistence layer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    KanbanService._instance = None
    yield  # type: ignore[misc]
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
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
        yield c  # type: ignore[misc]


def _create_board(client: TestClient) -> str:
    resp = client.post("/api/v1/kanban/boards", json={"name": "CriteriaTest"})
    assert resp.status_code == 201
    return resp.json()["board_id"]


class TestCompletionCriteriaRoundTrip:
    """Verify completion_criteria formats survive create → read → update → read."""

    def test_string_criteria_roundtrip(self, client: TestClient) -> None:
        board_id = _create_board(client)
        body = {"title": "StringCriteria", "completion_criteria": "file must exist"}
        resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=body)
        assert resp.status_code == 201
        task = resp.json()
        assert task["completion_criteria"] == "file must exist"

        get_resp = client.get(f"/api/v1/kanban/tasks/{task['task_id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["completion_criteria"] == "file must exist"

    def test_structured_criteria_with_int_timeout(self, client: TestClient) -> None:
        board_id = _create_board(client)
        criteria = [
            {"type": "shell", "command": "test -f /output.csv", "timeout_seconds": 30},
            {"type": "semantic", "criteria": "report is complete"},
        ]
        body = {"title": "StructuredCriteria", "completion_criteria": criteria}
        resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=body)
        assert resp.status_code == 201
        task = resp.json()
        assert isinstance(task["completion_criteria"], list)
        assert len(task["completion_criteria"]) == 2
        shell_item = task["completion_criteria"][0]
        assert shell_item["type"] == "shell"
        assert shell_item["timeout_seconds"] == 30

    def test_null_criteria_roundtrip(self, client: TestClient) -> None:
        board_id = _create_board(client)
        body = {"title": "NoCriteria"}
        resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=body)
        assert resp.status_code == 201
        assert resp.json()["completion_criteria"] is None

    def test_update_criteria_from_string_to_structured(self, client: TestClient) -> None:
        board_id = _create_board(client)
        create_resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Upgradeable", "completion_criteria": "basic check"},
        )
        task_id = create_resp.json()["task_id"]

        new_criteria = [
            {"type": "shell", "command": "curl -sf http://localhost:8080/health", "timeout_seconds": 10},
        ]
        update_resp = client.patch(
            f"/api/v1/kanban/tasks/{task_id}",
            json={"completion_criteria": new_criteria},
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert isinstance(updated["completion_criteria"], list)
        assert updated["completion_criteria"][0]["timeout_seconds"] == 10

    def test_clear_criteria_with_empty_string(self, client: TestClient) -> None:
        """PATCH with empty string clears completion_criteria (PATCH null = no-op)."""
        board_id = _create_board(client)
        create_resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Clearable", "completion_criteria": "check"},
        )
        task_id = create_resp.json()["task_id"]

        update_resp = client.patch(
            f"/api/v1/kanban/tasks/{task_id}",
            json={"completion_criteria": ""},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["completion_criteria"] is None

    def test_list_tasks_includes_criteria(self, client: TestClient) -> None:
        board_id = _create_board(client)
        client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "WithCriteria", "completion_criteria": "verify output"},
        )
        resp = client.get(f"/api/v1/kanban/boards/{board_id}/tasks")
        assert resp.status_code == 200
        tasks = resp.json()["items"]
        assert len(tasks) >= 1
        matched = [t for t in tasks if t["title"] == "WithCriteria"]
        assert matched[0]["completion_criteria"] == "verify output"

    def test_shell_only_structured_criteria(self, client: TestClient) -> None:
        board_id = _create_board(client)
        criteria = [
            {"type": "shell", "command": "test -f /a.txt", "timeout_seconds": 15},
            {"type": "shell", "command": "test -d /data"},
        ]
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "ShellOnly", "completion_criteria": criteria},
        )
        assert resp.status_code == 201
        task = resp.json()
        assert isinstance(task["completion_criteria"], list)
        assert len(task["completion_criteria"]) == 2
        assert task["completion_criteria"][0]["timeout_seconds"] == 15
        assert "timeout_seconds" not in task["completion_criteria"][1]

    def test_multi_shell_multi_semantic_criteria(self, client: TestClient) -> None:
        board_id = _create_board(client)
        criteria = [
            {"type": "shell", "command": "test -f /a.csv"},
            {"type": "shell", "command": "test -f /b.csv"},
            {"type": "semantic", "criteria": "CSV has headers"},
            {"type": "semantic", "criteria": "No empty rows"},
        ]
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "MultiMixed", "completion_criteria": criteria},
        )
        assert resp.status_code == 201
        stored = resp.json()["completion_criteria"]
        assert len(stored) == 4

    def test_special_chars_in_criteria(self, client: TestClient) -> None:
        board_id = _create_board(client)
        special = 'Check "quotes" and\nnewlines & <special>'
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "SpecialChars", "completion_criteria": special},
        )
        assert resp.status_code == 201
        assert resp.json()["completion_criteria"] == special

    def test_empty_list_criteria_stored_as_none(self, client: TestClient) -> None:
        """Empty list [] has no shell/semantic items, verifier treats as no criteria."""
        board_id = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "EmptyList", "completion_criteria": []},
        )
        assert resp.status_code == 201
