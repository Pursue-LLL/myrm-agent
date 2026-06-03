"""Shared fixtures for security API tests.

Bypasses auth middleware by patching resolve_identity to return a local user
identity for all requests, since TestClient does not send from a loopback IP.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from app.core.security.auth.identity import LOCAL_USER_ID


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = True


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch: pytest.MonkeyPatch):
    """Auto-applied fixture: make all TestClient requests pass auth."""
    from app.core.security.master_key import MasterKeyProvider

    MasterKeyProvider._reset_for_testing()
    monkeypatch.setenv("MYRM_MASTER_KEY", "test-master-key-for-vault-credentials")
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield
    MasterKeyProvider._reset_for_testing()
