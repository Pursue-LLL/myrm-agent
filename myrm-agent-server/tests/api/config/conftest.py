"""Shared fixtures for config API tests.

Bypasses auth middleware by patching resolve_identity to return a local user
identity for all requests, since TestClient does not send from a loopback IP.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.security.auth.identity import LOCAL_USER_ID


def cleanup_shared_test_db(db_path: Path) -> None:
    """Reset the global engine then delete the test DB files.

    The engine is a process-wide singleton backed by a connection pool. If a
    module-scoped teardown deletes ``data.db`` while pooled connections still
    point at the unlinked inode, the next module's ``init_database()`` sees
    the stale schema and skips ``create_all``, so fresh connections hit
    "no such table". Dispose the engine before unlinking to break that chain.
    """
    from app.platform_utils import reset_database_engine

    asyncio.run(reset_database_engine())
    db_path.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    admission_path: str | None = "loopback"


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Auto-applied fixture: make all TestClient requests pass auth."""
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield
