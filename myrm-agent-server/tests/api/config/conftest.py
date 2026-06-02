"""Shared fixtures for config API tests.

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


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Auto-applied fixture: make all TestClient requests pass auth."""
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield
