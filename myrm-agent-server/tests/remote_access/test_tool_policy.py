"""Remote tool policy overlay tests."""

from __future__ import annotations

from app.remote_access.tool_policy import merge_remote_security_overlay
from app.services.agent.params.converter import _apply_session_preset


def test_local_trusted_leaves_config_unchanged() -> None:
    raw = {"permissions": {"shell_exec": "ask"}}
    assert merge_remote_security_overlay(raw, trust_zone="local_trusted", admission_path="loopback_direct") == raw


def test_remote_exposed_denies_destructive_tools() -> None:
    merged = merge_remote_security_overlay(
        {"permissions": {"shell_exec": "ask"}},
        trust_zone="remote_exposed",
        admission_path="public_ingress",
    )
    assert merged is not None
    permissions = merged["permissions"]
    assert isinstance(permissions, dict)
    assert permissions["shell_exec"] == "deny"
    assert permissions["desktop_control"] == "deny"
    assert merged["yoloModeEnabled"] is False


def test_remote_overlay_after_session_preset_preserves_deny() -> None:
    """Regression: session preset applied BEFORE remote overlay must NOT bypass deny."""
    base = {"permissions": {"*": "ask"}}

    after_preset = _apply_session_preset(base, "accept_edits")
    assert after_preset is not None
    assert after_preset["permissions"]["shell_exec"] == "ask"

    final = merge_remote_security_overlay(
        after_preset,
        trust_zone="remote_exposed",
        admission_path="public_ingress",
    )
    assert final is not None
    assert final["permissions"]["shell_exec"] == "deny"
    assert final["permissions"]["desktop_control"] == "deny"
    assert final["permissions"]["code_interpreter"] == "deny"
    assert final["yoloModeEnabled"] is False


def test_session_preset_deep_merges_permissions() -> None:
    """Verify _apply_session_preset merges permissions at key level (not replace)."""
    base = {
        "permissions": {"*": "ask", "custom_tool": "deny"},
        "injectionPolicy": "strict",
    }
    result = _apply_session_preset(base, "accept_edits")
    assert result is not None
    assert result["permissions"]["custom_tool"] == "deny"
    assert result["permissions"]["shell_exec"] == "ask"
    assert result["permissions"]["*"] == "allow"
    assert result["injectionPolicy"] == "strict"


def test_session_preset_hitl_returns_base_unchanged() -> None:
    base = {"permissions": {"*": "ask"}}
    assert _apply_session_preset(base, "hitl") is base
    assert _apply_session_preset(base, None) is base


def test_session_preset_unknown_returns_base_unchanged() -> None:
    base = {"permissions": {"*": "ask"}}
    assert _apply_session_preset(base, "unknown_preset") is base


def test_explore_preset_plus_remote_exposed_both_deny_preserved() -> None:
    """Explore preset denies shell_exec; remote overlay also denies it. Both layers stack."""
    base = {"permissions": {"*": "ask"}}
    after_preset = _apply_session_preset(base, "explore")
    assert after_preset is not None
    assert after_preset["permissions"]["shell_exec"] == "deny"
    assert after_preset["permissions"]["file_write"] == "deny"

    final = merge_remote_security_overlay(
        after_preset,
        trust_zone="remote_exposed",
        admission_path="public_ingress",
    )
    assert final is not None
    assert final["permissions"]["shell_exec"] == "deny"
    assert final["permissions"]["file_write"] == "deny"
    assert final["permissions"]["desktop_control"] == "deny"
