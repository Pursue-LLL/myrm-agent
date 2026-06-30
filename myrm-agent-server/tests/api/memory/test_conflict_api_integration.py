"""Integration tests for memory conflict resolution API endpoints.

Full-path coverage:
- GET /conflicts: returns conflict list
- POST /conflicts/{id}/resolve with keep_old, keep_new, merge, discard_both
- 404 on unknown conflict_id
- 400 on merge without merged_content
- 400 on invalid resolution value
- Already-resolved conflict returns 404
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_memory_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


def _make_conflict_record(
    conflict_id: str = "conflict-1",
    *,
    status: str = "pending",
    old_memory_id: str = "old-mem-1",
    old_content: str = "Python is best",
    new_content: str = "Rust is better",
) -> MagicMock:
    record = MagicMock()
    record.id = conflict_id
    record.agent_id = "agent-1"
    record.memory_type = "semantic"
    record.content = new_content
    record.metadata_json = {"merge_suggestion": "Both have merits", "source": "consolidation_conflict"}
    record.confidence = 0.7
    record.status = status
    record.is_conflict = True
    record.conflict_old_memory_id = old_memory_id
    record.conflict_old_content = old_content
    record.conflict_accuracy_score = 0.7
    record.conflict_importance = 0.8
    record.conflict_auto_resolve_at = datetime.now(UTC) + timedelta(hours=72)
    record.created_at = datetime.now(UTC)
    record.resolved_at = None
    return record


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
    mock_manager.has_vector = True
    mock_manager.has_relational = True
    mock_manager.update_memory = AsyncMock()
    app.dependency_overrides[get_memory_manager] = lambda: mock_manager
    yield mock_manager
    app.dependency_overrides.pop(get_memory_manager, None)


class TestGetConflicts:
    """GET /api/v1/memory/conflicts"""

    def test_returns_conflicts_list(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        conflict = _make_conflict_record()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [conflict]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.get("/api/v1/memory/conflicts", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == "conflict-1"
        assert item["is_conflict"] is True
        assert item["conflict_old_memory_id"] == "old-mem-1"
        assert item["conflict_old_content"] == "Python is best"
        assert item["content"] == "Rust is better"

    def test_returns_empty_when_no_conflicts(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.get("/api/v1/memory/conflicts", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


class TestResolveConflict:
    """POST /api/v1/memory/conflicts/{conflict_id}/resolve"""

    def _setup_resolve_mocks(self, conflict: MagicMock) -> tuple[MagicMock, MagicMock]:
        """Setup shared mock pattern for resolve tests."""
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = conflict

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_select_result)
        mock_db.get = AsyncMock(return_value=conflict)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        return mock_db, mock_session_ctx

    def test_keep_old_resolution(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        override_memory_manager: AsyncMock,
    ) -> None:
        conflict = _make_conflict_record()
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "keep_old"},
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "resolved"
        assert data["resolution"] == "keep_old"
        override_memory_manager.update_memory.assert_not_called()

    def test_keep_new_resolution(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        override_memory_manager: AsyncMock,
    ) -> None:
        conflict = _make_conflict_record()
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "keep_new"},
            )

        assert resp.status_code == 200
        override_memory_manager.update_memory.assert_called_once_with(
            "old-mem-1", content="Rust is better",
        )

    def test_merge_resolution(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        override_memory_manager: AsyncMock,
    ) -> None:
        conflict = _make_conflict_record()
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "merge", "merged_content": "Both Python and Rust have merits"},
            )

        assert resp.status_code == 200
        override_memory_manager.update_memory.assert_called_once_with(
            "old-mem-1", content="Both Python and Rust have merits",
        )

    def test_merge_without_content_returns_400(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        conflict = _make_conflict_record()
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "merge"},
            )

        assert resp.status_code == 400

    def test_discard_both_resolution(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        override_memory_manager: AsyncMock,
    ) -> None:
        conflict = _make_conflict_record()
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "discard_both"},
            )

        assert resp.status_code == 200
        override_memory_manager.update_memory.assert_called_once_with(
            "old-mem-1", importance=0.01,
        )

    def test_invalid_resolution_returns_400(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        conflict = _make_conflict_record()
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "invalid_action"},
            )

        assert resp.status_code == 400

    def test_unknown_conflict_returns_404(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_select_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/nonexistent/resolve",
                headers=auth_headers,
                json={"resolution": "keep_old"},
            )

        assert resp.status_code == 404

    def test_already_resolved_conflict_returns_404(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        conflict = _make_conflict_record(status="resolved")
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "keep_old"},
            )

        assert resp.status_code == 404

    def test_keep_new_with_null_old_memory_id(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        override_memory_manager: AsyncMock,
    ) -> None:
        """keep_new does nothing when conflict_old_memory_id is None."""
        conflict = _make_conflict_record()
        conflict.conflict_old_memory_id = None
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "keep_new"},
            )

        assert resp.status_code == 200
        override_memory_manager.update_memory.assert_not_called()

    def test_discard_both_with_null_old_memory_id(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        override_memory_manager: AsyncMock,
    ) -> None:
        """discard_both does nothing when conflict_old_memory_id is None."""
        conflict = _make_conflict_record()
        conflict.conflict_old_memory_id = None
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "discard_both"},
            )

        assert resp.status_code == 200
        override_memory_manager.update_memory.assert_not_called()

    def test_resolve_response_contains_conflict_id(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Verify the response body includes the conflict_id for client-side reconciliation."""
        conflict = _make_conflict_record()
        _, mock_session_ctx = self._setup_resolve_mocks(conflict)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.post(
                "/api/v1/memory/conflicts/conflict-1/resolve",
                headers=auth_headers,
                json={"resolution": "keep_old"},
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["conflict_id"] == "conflict-1"
        assert data["status"] == "resolved"

    def test_multiple_conflicts_returned(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Multiple pending conflicts should all appear in the list."""
        c1 = _make_conflict_record("c1", old_content="fact A")
        c2 = _make_conflict_record("c2", old_content="fact B")
        c3 = _make_conflict_record("c3", old_content="fact C")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [c1, c2, c3]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.memory.operations.pending.get_session", return_value=mock_session_ctx):
            resp = client.get("/api/v1/memory/conflicts", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        ids = {item["id"] for item in data["items"]}
        assert ids == {"c1", "c2", "c3"}
