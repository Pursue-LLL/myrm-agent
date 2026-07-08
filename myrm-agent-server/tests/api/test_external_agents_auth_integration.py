"""Integration: external agent auth/status without mocking BackendDetector."""

from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import patch

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
def _bypass_auth() -> None:
    with patch("app.middleware.auth.resolve_identity", return_value=_FakeIdentity()):
        yield


@asynccontextmanager
async def _noop_lifespan(_app: object):
    yield


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    original = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.router.lifespan_context = original


@pytest.mark.integration
def test_auth_status_ready_for_delegation_live_detection(client: TestClient) -> None:
    """readyForDelegation must follow real PATH detection + credential store (no mocks)."""
    resp = client.get("/api/v1/external-agents/auth/status")
    assert resp.status_code == 200
    backends = {row["backend"]: row for row in resp.json()["backends"]}

    claude = backends["claude"]
    claude_on_path = shutil.which("claude") is not None
    assert claude["installed"] is claude_on_path
    assert claude["readyForDelegation"] is (
        claude["authenticated"] or claude["installed"]
    )

    for name, row in backends.items():
        assert row["readyForDelegation"] is (row["authenticated"] or row["installed"]), name
