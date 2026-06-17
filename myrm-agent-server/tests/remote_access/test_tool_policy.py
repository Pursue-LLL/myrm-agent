"""Remote tool policy overlay tests."""

from __future__ import annotations

from app.remote_access.tool_policy import merge_remote_security_overlay


def test_local_trusted_leaves_config_unchanged() -> None:
    raw = {"permissions": {"shell_exec": "ask"}}
    assert merge_remote_security_overlay(raw, trust_zone="local_trusted", admission_path="loopback_direct") == raw


def test_remote_exposed_denies_destructive_tools() -> None:
    merged = merge_remote_security_overlay(
        {"permissions": {"shell_exec": "ask", "file_read": "allow"}},
        trust_zone="remote_exposed",
        admission_path="public_ingress",
    )
    assert merged is not None
    permissions = merged["permissions"]
    assert isinstance(permissions, dict)
    assert permissions["shell_exec"] == "deny"
    assert permissions["desktop_control"] == "deny"
    assert permissions["file_read"] == "allow"
    assert len(permissions) == 10
    assert merged["yoloModeEnabled"] is False
    trust_ctx = merged.get("requestTrustContext")
    assert isinstance(trust_ctx, dict)
    assert trust_ctx["trustZone"] == "remote_exposed"
