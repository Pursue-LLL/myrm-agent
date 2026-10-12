"""Integration tests for Inherited Identity Guard API endpoints.

[INPUT]
- HTTP requests to /api/v1/security/inherited-identity/* endpoints.

[OUTPUT]
- Verified JSON responses for environment sanitization, session reference resolution,
  and official resume plan generation.

[POS]
- Server integration test suite for Herdr #4461 clear inherited terminal and session identity.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.inherited_identity_guard_router import (
    get_inherited_identity_guard_service,
)
from app.api.security.inherited_identity_guard_router import (
    router as inherited_identity_guard_router,
)
from app.services.security.inherited_identity_guard_service import (
    InheritedIdentityGuardService,
)


@pytest.fixture(scope="function")
def isolated_service() -> InheritedIdentityGuardService:
    """Fixture providing isolated service instance."""
    return InheritedIdentityGuardService()


@pytest.fixture(scope="function")
def client(isolated_service: InheritedIdentityGuardService) -> TestClient:
    """Fixture providing test client mounting inherited_identity_guard_router."""
    test_app = FastAPI(title="Inherited Identity Guard Test App")
    test_app.dependency_overrides[get_inherited_identity_guard_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        inherited_identity_guard_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_sanitize_env_endpoint_basic(client: TestClient) -> None:
    """Verify POST /sanitize-env purges inherited terminal and pane identity."""
    payload = {
        "dirty_env": {
            "PATH": "/usr/local/bin:/usr/bin",
            "USER": "developer",
            "TMUX": "/private/tmp/tmux-501/default,1234,0",
            "TMUX_PANE": "%1",
            "WT_SESSION": "4fa83c79-e58e-4a61-9c3f-913ea3295f9d",
            "GHOSTTY_PANE": "ghostty-pane-1",
            "MYRM_SESSION_ID": "parent-agent-session-99",
            "APP_DATA": "keep-this-variable",
        }
    }
    resp = client.post("/api/v1/security/inherited-identity/sanitize-env", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_isolated"] is True
    assert data["purged_count"] == 5
    assert "TMUX" in data["purged_keys"]
    assert "WT_SESSION" in data["purged_keys"]
    assert "MYRM_SESSION_ID" in data["purged_keys"]
    sanitized = data["sanitized_env"]
    assert sanitized["USER"] == "developer"
    assert sanitized["APP_DATA"] == "keep-this-variable"
    assert "TMUX" not in sanitized


def test_sanitize_env_endpoint_overrides_and_system_only(client: TestClient) -> None:
    """Verify POST /sanitize-env with extra overrides and allow_system_only flag."""
    payload = {
        "dirty_env": {
            "PATH": "/usr/bin",
            "HOME": "/home/developer",
            "CUSTOM_LEAK": "bad_token",
            "NON_SYS_VAR": "discard_me",
        },
        "extra_removals": ["CUSTOM_LEAK"],
        "extra_overrides": {"MYRM_SESSION_ID": "clean-child-sess-01"},
        "allow_system_only": True,
    }
    resp = client.post("/api/v1/security/inherited-identity/sanitize-env", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    sanitized = data["sanitized_env"]
    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["HOME"] == "/home/developer"
    assert sanitized["MYRM_SESSION_ID"] == "clean-child-sess-01"
    assert "CUSTOM_LEAK" not in sanitized
    assert "NON_SYS_VAR" not in sanitized


def test_resolve_session_ref_endpoint_success(client: TestClient) -> None:
    """Verify POST /resolve-session-ref parses valid official agent references."""
    # Claude ID
    payload_claude = {
        "source": "myrm:claude",
        "agent": "claude",
        "session_id": "sess-claude-turn-01",
    }
    resp = client.post(
        "/api/v1/security/inherited-identity/resolve-session-ref",
        json=payload_claude,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["session_ref"]["kind"] == "id"
    assert data["session_ref"]["value"] == "sess-claude-turn-01"

    # Pi Path
    payload_pi = {
        "source": "myrm:pi",
        "agent": "pi",
        "session_path": "/var/log/agents/pi-session.jsonl",
    }
    resp_pi = client.post(
        "/api/v1/security/inherited-identity/resolve-session-ref",
        json=payload_pi,
    )
    assert resp_pi.status_code == 200
    data_pi = resp_pi.json()
    assert data_pi["resolved"] is True
    assert data_pi["session_ref"]["kind"] == "path"
    assert data_pi["session_ref"]["value"] == "/var/log/agents/pi-session.jsonl"


def test_resolve_session_ref_endpoint_rejections(client: TestClient) -> None:
    """Verify POST /resolve-session-ref rejects unofficial or malformed inputs."""
    # Unofficial source
    payload_unauth = {
        "source": "unauthorized_proxy",
        "agent": "claude",
        "session_id": "sess-01",
    }
    resp = client.post(
        "/api/v1/security/inherited-identity/resolve-session-ref",
        json=payload_unauth,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is False
    assert "not an official" in data["reason"]

    # Relative path
    payload_rel = {
        "source": "myrm:pi",
        "agent": "pi",
        "session_path": "relative/path/pi.jsonl",
    }
    resp_rel = client.post(
        "/api/v1/security/inherited-identity/resolve-session-ref",
        json=payload_rel,
    )
    assert resp_rel.status_code == 200
    data_rel = resp_rel.json()
    assert data_rel["resolved"] is False


def test_create_resume_plan_endpoint_success(client: TestClient) -> None:
    """Verify POST /create-resume-plan produces validated resume command plan."""
    payload = {
        "source": "herdr:codex",
        "agent": "codex",
        "session_ref": {
            "kind": "id",
            "value": "codex-conversation-88",
        },
        "cwd": "/workspace/my-project",
    }
    resp = client.post(
        "/api/v1/security/inherited-identity/create-resume-plan", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["plan"]["agent"] == "codex"
    assert data["plan"]["argv"] == ["codex", "resume", "codex-conversation-88"]
    assert "herdr:codex" in data["plan"]["dedupe_key"]


def test_create_resume_plan_endpoint_injection_defense(client: TestClient) -> None:
    """Verify POST /create-resume-plan rejects injection attempts and unofficial sources."""
    # Apostrophe injection attempt
    payload_injection = {
        "source": "myrm:claude",
        "agent": "claude",
        "session_ref": {
            "kind": "id",
            "value": "sess-01' ; rm -rf /",
        },
    }
    resp = client.post(
        "/api/v1/security/inherited-identity/create-resume-plan",
        json=payload_injection,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is False
    assert "apostrophes" in data["reason"]

    # Unofficial source
    payload_unauth = {
        "source": "custom:claude",
        "agent": "claude",
        "session_ref": {
            "kind": "id",
            "value": "sess-01",
        },
    }
    resp_unauth = client.post(
        "/api/v1/security/inherited-identity/create-resume-plan",
        json=payload_unauth,
    )
    assert resp_unauth.status_code == 200
    data_unauth = resp_unauth.json()
    assert data_unauth["is_valid"] is False
    assert "not an official" in data_unauth["reason"]
