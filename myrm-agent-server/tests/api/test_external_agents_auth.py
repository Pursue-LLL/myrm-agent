"""Tests for external agent subscription-auth API endpoints.

[POS]
Tests for app/api/external_agents/: login-status reporting, SSE login event
relay, credential import/logout round-trip, and feed-to-missing-session guard.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="external_agents")
@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Make TestClient requests pass auth (TestClient is not seen as loopback)."""
    with patch("app.middleware.auth.resolve_identity", return_value=_FakeIdentity()):
        yield


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with HOME redirected to a temp dir so credential I/O is hermetic."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    original = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.router.lifespan_context = original


class TestAuthStatus:
    """GET /external-agents/auth/status."""

    def test_status_lists_known_backends(self, client):
        detector = MagicMock()
        detector.detect = AsyncMock(return_value=[])
        with patch(
            "myrm_agent_harness.toolkits.acp.backend_detector.BackendDetector",
            return_value=detector,
        ):
            resp = client.get("/api/v1/external-agents/auth/status")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["backends"]) == 4
        backends = {b["backend"]: b for b in body["backends"]}
        assert {"codex", "claude", "gemini", "qwen"} <= set(backends)
        codex = backends["codex"]
        assert codex["installed"] is False
        assert codex["authenticated"] is False
        assert codex["loginStrategy"] == "device_code"
        assert codex["scriptableLogin"] is True

    def test_status_reflects_installed_and_authenticated(self, client, tmp_path):
        (tmp_path / ".codex").mkdir()
        (tmp_path / ".codex" / "auth.json").write_text('{"token": "x"}', encoding="utf-8")
        found = MagicMock()
        found.name = "codex"
        found.path = "/usr/bin/codex"
        found.version = "1.2.3"
        detector = MagicMock()
        detector.detect = AsyncMock(return_value=[found])
        with patch(
            "myrm_agent_harness.toolkits.acp.backend_detector.BackendDetector",
            return_value=detector,
        ):
            resp = client.get("/api/v1/external-agents/auth/status")
        codex = {b["backend"]: b for b in resp.json()["backends"]}["codex"]
        assert codex["installed"] is True
        assert codex["path"] == "/usr/bin/codex"
        assert codex["authenticated"] is True


class TestAuthLogin:
    """POST /external-agents/auth/login (SSE)."""

    def test_login_streams_prompt_and_success(self, client):
        from myrm_agent_harness.toolkits.acp.auth import AuthEvent, AuthEventType

        class _FakeSession:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def run(self):
                yield AuthEvent(
                    AuthEventType.PROMPT,
                    message="Visit https://example/device",
                    url="https://example/device",
                    code="ABCD-1234",
                )
                yield AuthEvent(AuthEventType.SUCCESS, message="login complete")

            async def cancel(self) -> None:
                pass

        with patch("myrm_agent_harness.toolkits.acp.auth.CliLoginSession", _FakeSession):
            resp = client.post(
                "/api/v1/external-agents/auth/login",
                json={"command": "codex", "sessionId": "s1"},
            )
        assert resp.status_code == 200
        body = resp.text
        assert '"type": "prompt"' in body
        assert "ABCD-1234" in body
        assert '"type": "success"' in body

    def test_login_unknown_backend_returns_400(self, client):
        resp = client.post(
            "/api/v1/external-agents/auth/login",
            json={"command": "totally-unknown-cli", "sessionId": "s2"},
        )
        assert resp.status_code == 400


class TestAuthImportLogout:
    """POST /external-agents/auth/import and /logout."""

    def test_import_persists_then_logout_clears(self, client, tmp_path):
        cred = tmp_path / ".codex" / "auth.json"
        resp = client.post(
            "/api/v1/external-agents/auth/import",
            json={"backend": "codex", "content": '{"token": "abc"}'},
        )
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True
        assert cred.is_file()

        resp = client.post(
            "/api/v1/external-agents/auth/logout",
            json={"backend": "codex"},
        )
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False
        assert not cred.exists()

    def test_import_invalid_json_returns_400(self, client):
        resp = client.post(
            "/api/v1/external-agents/auth/import",
            json={"backend": "codex", "content": "not-json"},
        )
        assert resp.status_code == 400

    def test_import_unknown_backend_returns_400(self, client):
        resp = client.post(
            "/api/v1/external-agents/auth/import",
            json={"backend": "no-such-backend", "content": "x"},
        )
        assert resp.status_code == 400


class TestAuthFeed:
    """POST /external-agents/auth/login/{session_id}/feed."""

    def test_feed_missing_session_returns_404(self, client):
        resp = client.post(
            "/api/v1/external-agents/auth/login/nonexistent/feed",
            json={"text": "code"},
        )
        assert resp.status_code == 404
