"""API tests for /external-agents install SSE (WeSight #1)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID
from app.main import app


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"


@pytest.fixture(autouse=True)
def _bypass_auth() -> None:
    with patch("app.middleware.auth.resolve_identity", return_value=_FakeIdentity()):
        yield


@asynccontextmanager
async def _noop_lifespan(_app: object) -> AsyncIterator[None]:
    yield


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    original = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.router.lifespan_context = original


def _collect_sse_events(response) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in response.iter_lines():
        if not line or not line.startswith("data: "):
            continue
        events.append(json.loads(line[6:]))
    return events


def test_external_agent_auth_status(client: TestClient) -> None:
    """GET /auth/status returns known backends without error."""
    resp = client.get("/api/v1/external-agents/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "backends" in body
    names = {b["backend"] for b in body["backends"]}
    assert {"claude", "codex", "gemini"}.issubset(names)


def test_external_agent_install_unknown_backend_streams_error(client: TestClient) -> None:
    """Unknown backend yields progress error via SSE (no network install)."""
    with client.stream("POST", "/api/v1/external-agents/install/not-a-backend") as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    progress_msgs = [e.get("message") for e in events if e.get("type") == "progress"]
    assert any(isinstance(m, str) and "Unknown backend" in m for m in progress_msgs)
    assert any(e.get("type") == "success" for e in events)


def test_external_agent_install_claude_mocked_no_network(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install endpoint streams mocked toolchain progress (no real npm download)."""

    class FakeManager:
        async def install_backend(self, _backend: str) -> AsyncIterator[str]:
            yield "Mock: Node.js ready."
            yield "Mock: Successfully installed claude."

    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.acp.toolchains.IsolatedToolchainManager",
        FakeManager,
    )

    class FakeDetector:
        def invalidate_cache(self) -> None:
            pass

    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.acp.backend_detector.BackendDetector",
        FakeDetector,
    )

    with client.stream("POST", "/api/v1/external-agents/install/claude") as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    assert any(e.get("type") == "success" for e in events)
    messages = [e.get("message") for e in events if e.get("type") == "progress"]
    assert any("Mock: Successfully installed" in str(m) for m in messages)
