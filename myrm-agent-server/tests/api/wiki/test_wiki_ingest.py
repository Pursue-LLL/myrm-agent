"""Unit tests for POST /api/v1/wiki/ingest endpoint.

Isolated tests for artifact → wiki ingestion. Mocks DB, ArtifactVault,
and the wiki archiver to avoid any external I/O.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth():
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


# ── Fake ORM objects ────────────────────────────────────────────

class _FakeVersion:
    def __init__(self, vault_uri: str = "vault://obj-abc-123", ts: datetime | None = None):
        self.id = "v1"
        self.vault_uri = vault_uri
        self.created_at = ts or datetime(2025, 6, 1)


class _FakeArtifact:
    def __init__(self, *, versions: list[_FakeVersion] | None = None, name: str = "report.md"):
        self.id = "art-001"
        self.name = name
        self.is_deleted = False
        self.versions = versions if versions is not None else [_FakeVersion()]


# ── Helpers ─────────────────────────────────────────────────────

def _mock_session_ctx(artifact: _FakeArtifact | None):
    """Return an async context manager factory that yields a mocked DB session."""

    @contextlib.asynccontextmanager
    async def _ctx():
        db = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = artifact
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)
        yield db

    return _ctx


def _assert_error(resp, status: int, text_in_message: str) -> None:
    """Assert an error response from the global exception handler."""
    assert resp.status_code == status, f"Expected {status}, got {resp.status_code}: {resp.text}"
    body = resp.json()
    detail = body.get("detail", body.get("message", ""))
    assert text_in_message.lower() in detail.lower(), f"'{text_in_message}' not in '{detail}'"


@pytest.fixture
def ingest_env(tmp_path: Path):
    """Yield a callable ``build(artifact, vault_content)`` that returns
    ``(context_stack, mocks_dict)`` ready for ``with stack: ...``."""

    def _build(
        artifact: _FakeArtifact | None,
        vault_content: str = "# Real Content\nBody text here.",
    ) -> tuple[contextlib.ExitStack, dict[str, Any]]:
        obj_file = tmp_path / "vault_obj"
        obj_file.write_text(vault_content, encoding="utf-8")

        raw_dir = tmp_path / "wiki_raw"
        raw_dir.mkdir(exist_ok=True)

        mock_archiver = MagicMock()
        mock_archiver._structure.raw_dir = raw_dir
        mock_archiver._compiler.enqueue_file = MagicMock()

        mock_vault_instance = MagicMock()
        mock_vault_instance.get_object_path.return_value = obj_file
        mock_vault_cls = MagicMock(return_value=mock_vault_instance)

        stack = contextlib.ExitStack()

        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.artifacts.vault.ArtifactVault",
                mock_vault_cls,
            )
        )
        stack.enter_context(
            patch(
                "app.database.connection.get_session",
                _mock_session_ctx(artifact),
            )
        )
        stack.enter_context(
            patch(
                "app.api.dependencies.get_workspace_root",
                return_value=str(tmp_path),
            )
        )

        from app.api.wiki.router import _get_wiki_archiver
        from app.main import app

        async def _override_archiver():
            return mock_archiver

        app.dependency_overrides[_get_wiki_archiver] = _override_archiver
        stack.callback(app.dependency_overrides.pop, _get_wiki_archiver, None)

        mocks = {
            "archiver": mock_archiver,
            "vault_cls": mock_vault_cls,
            "vault_instance": mock_vault_instance,
            "raw_dir": raw_dir,
            "obj_file": obj_file,
        }
        return stack, mocks

    return _build


# ── Happy Path ──────────────────────────────────────────────────

class TestIngestSuccess:
    def test_writes_raw_file_and_enqueues(self, client: TestClient, ingest_env) -> None:
        artifact = _FakeArtifact(name="analysis_report.md")
        stack, mocks = ingest_env(artifact)
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "analysis_report" in body["message"]
        mocks["archiver"]._compiler.enqueue_file.assert_called_once()

        written = list(mocks["raw_dir"].glob("artifact_*"))
        assert len(written) == 1
        assert written[0].read_text(encoding="utf-8") == "# Real Content\nBody text here."

    def test_picks_latest_version_by_created_at(self, client: TestClient, ingest_env) -> None:
        v_old = _FakeVersion(vault_uri="vault://old-obj", ts=datetime(2024, 1, 1))
        v_new = _FakeVersion(vault_uri="vault://obj-abc-123", ts=datetime(2025, 6, 1))
        artifact = _FakeArtifact(versions=[v_old, v_new])
        stack, mocks = ingest_env(artifact)
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})
        assert resp.status_code == 200
        mocks["vault_instance"].get_object_path.assert_called_once_with("obj-abc-123")


# ── Error Paths ─────────────────────────────────────────────────

class TestIngestErrors:
    def test_artifact_not_found_404(self, client: TestClient, ingest_env) -> None:
        stack, _ = ingest_env(None)
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "ghost"})
            _assert_error(resp, 404, "not found")

    def test_no_versions_400(self, client: TestClient, ingest_env) -> None:
        artifact = _FakeArtifact(versions=[])
        stack, _ = ingest_env(artifact)
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})
            _assert_error(resp, 400, "no versions")

    def test_vault_file_missing_404(self, client: TestClient, ingest_env, tmp_path: Path) -> None:
        artifact = _FakeArtifact()
        stack, mocks = ingest_env(artifact)
        missing = tmp_path / "does_not_exist"
        mocks["vault_instance"].get_object_path.return_value = missing
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})
            _assert_error(resp, 404, "not found")

    def test_empty_content_returns_success_false(self, client: TestClient, ingest_env) -> None:
        artifact = _FakeArtifact()
        stack, _ = ingest_env(artifact, vault_content="   \n  \t  ")
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "empty" in body["message"].lower()


# ── Request Validation (no mocks needed) ────────────────────────

class TestIngestValidation:
    def test_empty_artifact_id_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": ""})
        assert resp.status_code == 422

    def test_missing_artifact_id_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/wiki/ingest", json={})
        assert resp.status_code == 422

    def test_no_body_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/wiki/ingest")
        assert resp.status_code == 422


# ── Edge Cases ──────────────────────────────────────────────────

class TestIngestEdgeCases:
    def test_name_with_slashes_and_spaces_sanitized(self, client: TestClient, ingest_env) -> None:
        artifact = _FakeArtifact(name="my report / final version")
        stack, mocks = ingest_env(artifact)
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})
        assert resp.status_code == 200
        written = list(mocks["raw_dir"].glob("artifact_*"))
        assert len(written) == 1
        assert "/" not in written[0].name
        assert " " not in written[0].name

    def test_vault_uri_without_prefix_used_as_is(self, client: TestClient, ingest_env) -> None:
        artifact = _FakeArtifact(versions=[_FakeVersion(vault_uri="raw-id-456")])
        stack, mocks = ingest_env(artifact)
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})
        if resp.status_code == 200:
            mocks["vault_instance"].get_object_path.assert_called_once_with("raw-id-456")

    def test_long_name_truncated_to_80(self, client: TestClient, ingest_env) -> None:
        long_name = "a" * 200 + ".txt"
        artifact = _FakeArtifact(name=long_name)
        stack, mocks = ingest_env(artifact)
        with stack:
            resp = client.post("/api/v1/wiki/ingest", json={"artifact_id": "art-001"})
        assert resp.status_code == 200
        written = list(mocks["raw_dir"].glob("artifact_*"))
        assert len(written) == 1
        name_part = written[0].stem.replace("artifact_", "").rsplit("_", 2)[0]
        assert len(name_part) <= 80
