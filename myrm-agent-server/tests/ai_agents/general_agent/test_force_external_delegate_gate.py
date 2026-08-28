"""Unit tests for force_external_agent security gate in stream_pipeline."""

from __future__ import annotations

from types import SimpleNamespace

from myrm_agent_harness.agent.security.types import SecurityConfig


def _wrapper_with_config(config: SecurityConfig) -> SimpleNamespace:
    from myrm_agent_harness.agent.security.config import security_config_to_dict

    return SimpleNamespace(security_config_raw=security_config_to_dict(config))


def test_force_external_denied_on_readonly_profile() -> None:
    from app.ai_agents.general_agent.stream_pipeline import _force_external_delegate_denial_reason

    reason = _force_external_delegate_denial_reason(
        _wrapper_with_config(SecurityConfig.readonly()),
        "echo-cli",
    )
    assert reason is not None
    assert "deny" in reason.lower()


def test_force_external_denied_on_workspace_ask_profile() -> None:
    from app.ai_agents.general_agent.stream_pipeline import _force_external_delegate_denial_reason

    config = SecurityConfig.workspace(allowed_roots=("/tmp",))
    reason = _force_external_delegate_denial_reason(
        _wrapper_with_config(config),
        "echo-cli",
    )
    assert reason is not None
    assert "ask" in reason.lower()


def test_force_external_allowed_on_full_access_profile() -> None:
    from app.ai_agents.general_agent.stream_pipeline import _force_external_delegate_denial_reason

    reason = _force_external_delegate_denial_reason(
        _wrapper_with_config(SecurityConfig.full_access()),
        "echo-cli",
    )
    assert reason is None
