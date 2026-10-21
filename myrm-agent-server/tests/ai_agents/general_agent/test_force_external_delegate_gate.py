"""Unit tests for force_external_agent security gate in stream_pipeline."""

from __future__ import annotations

from types import SimpleNamespace

from app.ai_agents.general_agent.stream_pipeline import _force_external_delegate_denial_reason


def _security_raw(*, invoke_external: str) -> dict[str, object]:
    return {
        "capabilities": [{"permission": "*", "pattern": "*"}],
        "permissions": {
            "spawn_subagent": "allow",
            "invoke_external_agent": invoke_external,
            "file_write": "ask",
            "shell_exec": "ask",
        },
        "yoloModeEnabled": False,
        "autoModeEnabled": False,
    }


def test_force_external_denied_when_security_config_missing() -> None:
    agent = SimpleNamespace(security_config_raw=None)
    reason = _force_external_delegate_denial_reason(agent, "echo-cli")
    assert reason is not None
    assert "security config missing" in reason.lower()


def test_force_external_allowed_when_invoke_external_allowed() -> None:
    agent = SimpleNamespace(security_config_raw=_security_raw(invoke_external="allow"))
    reason = _force_external_delegate_denial_reason(agent, "echo-cli")
    assert reason is None


def test_force_external_denied_when_invoke_external_ask() -> None:
    agent = SimpleNamespace(security_config_raw=_security_raw(invoke_external="ask"))
    reason = _force_external_delegate_denial_reason(agent, "echo-cli")
    assert reason is not None
    assert "ask" in reason.lower()
