"""Unit tests for #47 — task result/metadata editing via PATCH + EDITED event.

Covers:
- PATCH /tasks/{task_id} with result field
- PATCH /tasks/{task_id} with metadata merge
- EDITED event emission on result/metadata change
- Validation of result max_length (10000)
- No EDITED event when result/metadata not in payload
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
    yield
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
        yield c


def _create_board(client: TestClient, name: str = "TestBoard") -> dict[str, object]:
    resp = client.post("/api/v1/kanban/boards", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_task(client: TestClient, board_id: str, title: str = "Task") -> dict[str, object]:
    resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json={"title": title})
    assert resp.status_code == 201
    return resp.json()


class TestPatchResultField:
    """PATCH /tasks/{task_id} with result field."""

    def test_patch_result_updates_task(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "ResultTask")
        tid = str(task["task_id"])

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"result": "Fixed the hallucination"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "Fixed the hallucination"

    def test_patch_result_persists_on_get(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "PersistResult")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": "persisted value"})

        resp = client.get(f"/api/v1/kanban/tasks/{tid}")
        assert resp.status_code == 200
        assert resp.json()["result"] == "persisted value"

    def test_patch_result_overwrite(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "OverwriteResult")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": "v1"})
        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": "v2"})

        resp = client.get(f"/api/v1/kanban/tasks/{tid}")
        assert resp.json()["result"] == "v2"

    def test_patch_result_empty_string(self, client: TestClient) -> None:
        """Empty string is a valid result value (clears display)."""
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "EmptyResult")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": "something"})
        resp = client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": ""})
        assert resp.status_code == 200


class TestPatchMetadataField:
    """PATCH /tasks/{task_id} with metadata merge."""

    def test_patch_metadata_merges(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "MetaTask")
        tid = str(task["task_id"])

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"metadata": {"changed_files": ["a.py"]}},
        )
        assert resp.status_code == 200
        assert resp.json()["metadata"]["changed_files"] == ["a.py"]

    def test_patch_metadata_additive(self, client: TestClient) -> None:
        """Second metadata PATCH merges into existing, not replaces."""
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "AdditiveMeta")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"metadata": {"key1": "val1"}})
        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"metadata": {"key2": "val2"}})

        resp = client.get(f"/api/v1/kanban/tasks/{tid}")
        meta = resp.json()["metadata"]
        assert meta["key1"] == "val1"
        assert meta["key2"] == "val2"

    def test_patch_metadata_overwrite_key(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "OverwriteMeta")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"metadata": {"k": "old"}})
        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"metadata": {"k": "new"}})

        resp = client.get(f"/api/v1/kanban/tasks/{tid}")
        assert resp.json()["metadata"]["k"] == "new"


class TestPatchResultAndMetadataCombined:
    """PATCH with both result and metadata in a single request."""

    def test_patch_both_fields(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "BothFields")
        tid = str(task["task_id"])

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={
                "result": "Combined update",
                "metadata": {"test_count": 5},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "Combined update"
        assert data["metadata"]["test_count"] == 5


class TestEditedEvent:
    """EDITED event emission when result/metadata change."""

    def test_edited_event_on_result_change(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "EditEvent")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": "new result"})

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        edited_events = [e for e in events if e["kind"] == "edited"]
        assert len(edited_events) == 1
        assert "result" in edited_events[0]["payload"]["fields"]

    def test_edited_event_on_metadata_change(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "MetaEvent")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"metadata": {"x": 1}})

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        edited_events = [e for e in events if e["kind"] == "edited"]
        assert len(edited_events) == 1
        assert "metadata" in edited_events[0]["payload"]["fields"]

    def test_edited_event_both_fields(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "BothEvent")
        tid = str(task["task_id"])

        client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"result": "r", "metadata": {"a": 1}},
        )

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        edited_events = [e for e in events if e["kind"] == "edited"]
        assert len(edited_events) == 1
        fields = edited_events[0]["payload"]["fields"]
        assert "result" in fields
        assert "metadata" in fields

    def test_no_edited_event_on_title_only(self, client: TestClient) -> None:
        """Title-only PATCH should not emit EDITED event."""
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "TitleOnly")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"title": "Renamed"})

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        edited_events = [e for e in events if e["kind"] == "edited"]
        assert len(edited_events) == 0

    def test_multiple_edits_create_multiple_events(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "MultiEdit")
        tid = str(task["task_id"])

        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": "edit1"})
        client.patch(f"/api/v1/kanban/tasks/{tid}", json={"result": "edit2"})

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        edited_events = [e for e in events if e["kind"] == "edited"]
        assert len(edited_events) == 2


class TestResultValidation:
    """Schema validation for result field."""

    def test_result_max_length(self, client: TestClient) -> None:
        """result exceeding 10000 chars should be rejected by Pydantic."""
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "MaxLen")
        tid = str(task["task_id"])

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"result": "x" * 10001},
        )
        assert resp.status_code == 422

    def test_result_at_max_length(self, client: TestClient) -> None:
        """result exactly at 10000 chars should be accepted."""
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "ExactMax")
        tid = str(task["task_id"])

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"result": "x" * 10000},
        )
        assert resp.status_code == 200


class TestNullResultNotTriggerEdit:
    """Ensure null result in PATCH does not trigger EDITED event."""

    def test_null_result_no_edit(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "NullResult")
        tid = str(task["task_id"])

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        edited_events = [e for e in events if e["kind"] == "edited"]
        assert len(edited_events) == 0


class TestEdgeCases:
    """Edge cases for result/metadata editing."""

    def test_result_with_special_characters(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "SpecialChars")
        tid = str(task["task_id"])

        special = 'Result with "quotes", <tags>, & ampersands, 中文字符, emoji 🎉'
        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"result": special},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == special

    def test_metadata_nested_objects(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "NestedMeta")
        tid = str(task["task_id"])

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"metadata": {"nested": {"a": 1, "b": [2, 3]}}},
        )
        assert resp.status_code == 200
        assert resp.json()["metadata"]["nested"] == {"a": 1, "b": [2, 3]}

    def test_patch_result_with_title_no_double_event(self, client: TestClient) -> None:
        """PATCH with result + title should emit exactly one EDITED event."""
        board = _create_board(client)
        task = _create_task(client, str(board["board_id"]), "TitleAndResult")
        tid = str(task["task_id"])

        client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"title": "New Title", "result": "New Result"},
        )

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        edited_events = [e for e in events if e["kind"] == "edited"]
        assert len(edited_events) == 1
        assert edited_events[0]["payload"]["fields"] == ["result"]

    def test_metadata_preserves_existing_keys(self, client: TestClient) -> None:
        """New metadata merge must not wipe completion_criteria set on create."""
        board = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board['board_id']}/tasks",
            json={"title": "WithCriteria", "completion_criteria": "Must pass CI"},
        )
        assert resp.status_code == 201
        tid = str(resp.json()["task_id"])

        client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"metadata": {"extra": "data"}},
        )

        data = client.get(f"/api/v1/kanban/tasks/{tid}").json()
        assert data["metadata"].get("completion_criteria") == "Must pass CI"
        assert data["metadata"].get("extra") == "data"

    def test_nonexistent_task_patch(self, client: TestClient) -> None:
        resp = client.patch(
            "/api/v1/kanban/tasks/nonexistent_id",
            json={"result": "should fail"},
        )
        assert resp.status_code == 404
