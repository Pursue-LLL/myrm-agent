"""Unit tests for InheritedIdentityGuardService in myrm-agent-server.

[INPUT]
- InheritedIdentityGuardService, request DTOs.

[OUTPUT]
- Verified environment sanitization, session reference resolution, and resume plans.

[POS]
- Server unit test suite for Herdr #4461 clear inherited terminal and session identity.
"""

from __future__ import annotations

import pytest

from app.schemas.inherited_identity_guard import (
    AgentSessionRefDto,
    CreateResumePlanRequest,
    ResolveSessionRefRequest,
    SanitizeEnvRequest,
    SessionRefKindDto,
)
from app.services.security.inherited_identity_guard_service import (
    InheritedIdentityGuardService,
)


@pytest.fixture
def service() -> InheritedIdentityGuardService:
    """Fixture providing a fresh InheritedIdentityGuardService instance."""
    return InheritedIdentityGuardService()


def test_sanitize_environment_default_purgings(
    service: InheritedIdentityGuardService,
) -> None:
    """Verify that known inherited terminal pane and session variables are removed."""
    req = SanitizeEnvRequest(
        dirty_env={
            "PATH": "/usr/bin:/bin",
            "USER": "bob",
            "TMUX": "/tmp/tmux-1000/default",
            "TMUX_PANE": "%0",
            "WT_SESSION": "uuid-1234",
            "WEZTERM_PANE": "pane-9",
            "GHOSTTY_PANE": "ghostty-0",
            "TERM_SESSION_ID": "term-session-id",
            "MYRM_SESSION_ID": "myrm-sess-parent",
            "CUSTOM_VAR": "keep",
        }
    )
    resp = service.sanitize_environment(req)

    assert resp.is_isolated is True
    assert "PATH" in resp.sanitized_env
    assert "USER" in resp.sanitized_env
    assert "CUSTOM_VAR" in resp.sanitized_env
    assert "TMUX" not in resp.sanitized_env
    assert "TMUX_PANE" not in resp.sanitized_env
    assert "WT_SESSION" not in resp.sanitized_env
    assert "WEZTERM_PANE" not in resp.sanitized_env
    assert "GHOSTTY_PANE" not in resp.sanitized_env
    assert "TERM_SESSION_ID" not in resp.sanitized_env
    assert "MYRM_SESSION_ID" not in resp.sanitized_env
    assert resp.purged_count == 7
    assert len(resp.purged_keys) == 7


def test_sanitize_environment_with_overrides_and_system_only(
    service: InheritedIdentityGuardService,
) -> None:
    """Verify custom removals, explicit override injection, and system_only filtering."""
    req = SanitizeEnvRequest(
        dirty_env={
            "PATH": "/usr/bin",
            "HOME": "/home/bob",
            "CUSTOM_LEAK": "leak_val",
            "RANDOM_APP": "app_val",
        },
        extra_removals=["CUSTOM_LEAK"],
        extra_overrides={"MYRM_SESSION_ID": "child-session-01"},
        allow_system_only=True,
    )
    resp = service.sanitize_environment(req)

    assert resp.sanitized_env["PATH"] == "/usr/bin"
    assert resp.sanitized_env["HOME"] == "/home/bob"
    assert resp.sanitized_env["MYRM_SESSION_ID"] == "child-session-01"
    assert "CUSTOM_LEAK" not in resp.sanitized_env
    assert "RANDOM_APP" not in resp.sanitized_env
    assert "CUSTOM_LEAK" in resp.purged_keys
    assert "RANDOM_APP" in resp.purged_keys


def test_resolve_session_reference_official_sources(
    service: InheritedIdentityGuardService,
) -> None:
    """Verify resolution of official agent session references."""
    # Official Claude ID
    req_claude = ResolveSessionRefRequest(
        source="myrm:claude",
        agent="claude",
        session_id="claude-sess-99",
    )
    resp_claude = service.resolve_session_reference(req_claude)
    assert resp_claude.resolved is True
    assert resp_claude.session_ref is not None
    assert resp_claude.session_ref.kind == SessionRefKindDto.ID
    assert resp_claude.session_ref.value == "claude-sess-99"

    # Official Pi Path
    req_pi = ResolveSessionRefRequest(
        source="myrm:pi",
        agent="pi",
        session_path="/tmp/pi-sess.jsonl",
    )
    resp_pi = service.resolve_session_reference(req_pi)
    assert resp_pi.resolved is True
    assert resp_pi.session_ref is not None
    assert resp_pi.session_ref.kind == SessionRefKindDto.PATH
    assert resp_pi.session_ref.value == "/tmp/pi-sess.jsonl"


def test_resolve_session_reference_rejections(
    service: InheritedIdentityGuardService,
) -> None:
    """Verify rejection of unofficial sources and invalid parameter formats."""
    # Unofficial source
    req_unauth = ResolveSessionRefRequest(
        source="unauthorized_proxy",
        agent="claude",
        session_id="sess-1",
    )
    resp_unauth = service.resolve_session_reference(req_unauth)
    assert resp_unauth.resolved is False
    assert "not an official" in str(resp_unauth.reason)

    # Path reference for ID-only agent
    req_path_claude = ResolveSessionRefRequest(
        source="myrm:claude",
        agent="claude",
        session_path="/tmp/claude.jsonl",
    )
    resp_path_claude = service.resolve_session_reference(req_path_claude)
    assert resp_path_claude.resolved is False

    # Invalid session ID with control character
    req_ctrl = ResolveSessionRefRequest(
        source="myrm:codex",
        agent="codex",
        session_id="bad\x00id",
    )
    resp_ctrl = service.resolve_session_reference(req_ctrl)
    assert resp_ctrl.resolved is False


def test_generate_resume_plan_success(
    service: InheritedIdentityGuardService,
) -> None:
    """Verify successful generation of validated agent resume plans."""
    req_codex = CreateResumePlanRequest(
        source="herdr:codex",
        agent="codex",
        session_ref=AgentSessionRefDto(
            kind=SessionRefKindDto.ID, value="codex-sess-55"
        ),
    )
    resp_codex = service.generate_resume_plan(req_codex)
    assert resp_codex.is_valid is True
    assert resp_codex.plan is not None
    assert resp_codex.plan.argv == ["codex", "resume", "codex-sess-55"]
    assert "herdr:codex" in resp_codex.plan.dedupe_key


def test_generate_resume_plan_rejections(
    service: InheritedIdentityGuardService,
) -> None:
    """Verify rejection of resume plans with malicious or injection arguments."""
    # Unofficial source
    req_unauth = CreateResumePlanRequest(
        source="evil:codex",
        agent="codex",
        session_ref=AgentSessionRefDto(
            kind=SessionRefKindDto.ID, value="sess-1"
        ),
    )
    resp_unauth = service.generate_resume_plan(req_unauth)
    assert resp_unauth.is_valid is False
    assert "not an official" in str(resp_unauth.reason)

    # Shell escape with single quote
    req_quote = CreateResumePlanRequest(
        source="myrm:claude",
        agent="claude",
        session_ref=AgentSessionRefDto(
            kind=SessionRefKindDto.ID, value="can't_hack"
        ),
    )
    resp_quote = service.generate_resume_plan(req_quote)
    assert resp_quote.is_valid is False
    assert "apostrophes" in str(resp_quote.reason)
