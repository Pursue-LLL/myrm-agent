"""Unit tests for E2EE bootstrap path authorization."""

from __future__ import annotations

from app.remote_access.mobile_gate import (
    E2EE_HANDSHAKE_PATH,
    E2EE_PUBLIC_KEY_PATH,
    is_e2ee_bootstrap_path,
)


def test_e2ee_bootstrap_paths() -> None:
    assert is_e2ee_bootstrap_path(E2EE_PUBLIC_KEY_PATH)
    assert is_e2ee_bootstrap_path(E2EE_HANDSHAKE_PATH)
    assert not is_e2ee_bootstrap_path("/api/v1/remote-access/mobile/sessions")
