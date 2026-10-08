"""Endpoint tests for the pending-memory approval API.

Covers the harness-backed ``/memory/pending`` surface: listing, single and batch
approve/reject, and the error mapping that distinguishes a missing record (404)
from a server-side failure (500).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryNotFoundError
from myrm_agent_harness.toolkits.memory.types import MemoryType, PendingRecord

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_memory_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test_token"}


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield
    app.dependency_overrides.pop(get_deploy_identity, None)


@pytest.fixture(autouse=True)
def override_memory_manager():
    mock_manager = AsyncMock(spec=MemoryManager)
    mock_manager.approval_required = True
    app.dependency_overrides[get_memory_manager] = lambda: mock_manager
    yield mock_manager
    app.dependency_overrides.pop(get_memory_manager, None)


def _pending_record(memory_id: str = "p-1") -> PendingRecord:
    return PendingRecord(
        id=memory_id,
        memory_type=MemoryType.SEMANTIC,
        content="User prefers Rust",
        memory_data={"content": "User prefers Rust", "importance": 0.7},
    )


class TestGetPending:
    def test_returns_items(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.list_pending = AsyncMock(return_value=[_pending_record()])
        override_memory_manager.count_pending = AsyncMock(return_value=1)

        resp = client.get("/api/v1/memory/pending", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "p-1"

    def test_empty_when_approval_disabled(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.approval_required = False

        resp = client.get("/api/v1/memory/pending", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}


class TestApprovePending:
    def test_approve_success(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.approve = AsyncMock(return_value=None)

        with (
            patch(
                "app.api.memory.operations.pending._load_pending_memory",
                AsyncMock(return_value=_pending_record()),
            ),
            patch("app.api.memory.operations.pending.record_experience_event", AsyncMock()),
            patch("app.api.memory.operations.pending._record_pending_event", AsyncMock()),
        ):
            resp = client.post("/api/v1/memory/pending/p-1/approve", headers=auth_headers, json={})

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "approved"
        override_memory_manager.approve.assert_awaited_once_with("p-1", edited_content=None)

    def test_approve_forwards_reviewer_edit(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.approve = AsyncMock(return_value=None)

        with (
            patch(
                "app.api.memory.operations.pending._load_pending_memory",
                AsyncMock(return_value=_pending_record()),
            ),
            patch("app.api.memory.operations.pending.record_experience_event", AsyncMock()),
            patch("app.api.memory.operations.pending._record_pending_event", AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/memory/pending/p-1/approve",
                headers=auth_headers,
                json={"edited_content": "Reworded fact"},
            )

        assert resp.status_code == 200
        override_memory_manager.approve.assert_awaited_once_with("p-1", edited_content="Reworded fact")

    def test_unusable_edit_maps_to_400(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.approve = AsyncMock(side_effect=ValueError("This proposal has no editable content"))

        with patch(
            "app.api.memory.operations.pending._load_pending_memory",
            AsyncMock(return_value=_pending_record()),
        ):
            resp = client.post(
                "/api/v1/memory/pending/p-1/approve",
                headers=auth_headers,
                json={"edited_content": "anything"},
            )

        assert resp.status_code == 400
        assert "no editable content" in resp.text

    def test_missing_record_maps_to_404(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.approve = AsyncMock(side_effect=MemoryNotFoundError("gone"))

        with patch(
            "app.api.memory.operations.pending._load_pending_memory",
            AsyncMock(return_value=None),
        ):
            resp = client.post("/api/v1/memory/pending/p-1/approve", headers=auth_headers, json={})

        assert resp.status_code == 404

    def test_unexpected_failure_maps_to_500(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.approve = AsyncMock(side_effect=RuntimeError("storage down"))

        with patch(
            "app.api.memory.operations.pending._load_pending_memory",
            AsyncMock(return_value=None),
        ):
            resp = client.post("/api/v1/memory/pending/p-1/approve", headers=auth_headers, json={})

        assert resp.status_code == 500


class TestRejectPending:
    def test_reject_success(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.reject = AsyncMock(return_value=None)

        with (
            patch(
                "app.api.memory.operations.pending._load_pending_memory",
                AsyncMock(return_value=_pending_record()),
            ),
            patch("app.api.memory.operations.pending.record_experience_event", AsyncMock()),
            patch("app.api.memory.operations.pending._record_pending_event", AsyncMock()),
        ):
            resp = client.post("/api/v1/memory/pending/p-1/reject", headers=auth_headers, json={})

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "rejected"

    def test_not_found_maps_to_404(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.reject = AsyncMock(side_effect=MemoryNotFoundError("gone"))

        with patch(
            "app.api.memory.operations.pending._load_pending_memory",
            AsyncMock(return_value=None),
        ):
            resp = client.post("/api/v1/memory/pending/p-1/reject", headers=auth_headers, json={})

        assert resp.status_code == 404


class TestBatchPending:
    def test_batch_approve(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.batch_approve = AsyncMock(return_value=(2, []))

        with (
            patch(
                "app.api.memory.operations.pending._load_pending_memory",
                AsyncMock(return_value=_pending_record()),
            ),
            patch("app.api.memory.operations.pending.record_experience_event", AsyncMock()),
            patch("app.api.memory.operations.pending._record_pending_event", AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/memory/pending/batch/approve",
                headers=auth_headers,
                json={"memory_ids": ["p-1", "p-2"]},
            )

        assert resp.status_code == 200
        assert resp.json()["success_count"] == 2

    def test_batch_reject(self, client: TestClient, auth_headers: dict[str, str], override_memory_manager) -> None:
        override_memory_manager.batch_reject = AsyncMock(return_value=2)

        with (
            patch(
                "app.api.memory.operations.pending._load_pending_memory",
                AsyncMock(return_value=None),
            ),
            patch("app.api.memory.operations.pending.record_experience_event", AsyncMock()),
            patch("app.api.memory.operations.pending._record_pending_event", AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/memory/pending/batch/reject",
                headers=auth_headers,
                json={"memory_ids": ["p-1", "p-2"]},
            )

        assert resp.status_code == 200
        assert resp.json()["success_count"] == 2

    def test_approve_without_approval_enabled_returns_400(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.approval_required = False

        resp = client.post("/api/v1/memory/pending/p-1/approve", headers=auth_headers, json={})

        assert resp.status_code == 400

    def test_batch_approve_without_approval_enabled_returns_400(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.approval_required = False

        resp = client.post(
            "/api/v1/memory/pending/batch/approve",
            headers=auth_headers,
            json={"memory_ids": ["p-1"]},
        )

        assert resp.status_code == 400

    def test_batch_reject_without_approval_enabled_returns_400(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.approval_required = False

        resp = client.post(
            "/api/v1/memory/pending/batch/reject",
            headers=auth_headers,
            json={"memory_ids": ["p-1"]},
        )

        assert resp.status_code == 400

    def test_batch_approve_reports_partial_failure(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.batch_approve = AsyncMock(return_value=(1, ["p-2"]))

        with (
            patch(
                "app.api.memory.operations.pending._load_pending_memory",
                AsyncMock(return_value=_pending_record()),
            ),
            patch("app.api.memory.operations.pending.record_experience_event", AsyncMock()),
            patch("app.api.memory.operations.pending._record_pending_event", AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/memory/pending/batch/approve",
                headers=auth_headers,
                json={"memory_ids": ["p-1", "p-2"]},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success_count"] == 1
        assert body["failed_ids"] == ["p-2"]

    def test_batch_reject_reports_failures(
        self, client: TestClient, auth_headers: dict[str, str], override_memory_manager
    ) -> None:
        override_memory_manager.batch_reject = AsyncMock(return_value=1)

        rejected = _pending_record("p-1")
        rejected.status = "rejected"
        # p-2 stays pending, so the ledger loop must skip it.
        pending = _pending_record("p-2")

        async def _load(memory_id: str) -> PendingRecord:
            return rejected if memory_id == "p-1" else pending

        with (
            patch("app.api.memory.operations.pending._load_pending_memory", _load),
            patch("app.api.memory.operations.pending.record_experience_event", AsyncMock()),
            patch("app.api.memory.operations.pending._record_pending_event", AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/memory/pending/batch/reject",
                headers=auth_headers,
                json={"memory_ids": ["p-1", "p-2"]},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success_count"] == 1
        assert body["failed_count"] == 1
