"""Evolution API tests — bypass auth for TestClient (non-loopback client)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest
from sqlalchemy import delete

from app.core.security.auth.identity import LOCAL_USER_ID
from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"


@pytest.fixture(autouse=True)
def _bypass_auth():
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture(autouse=True)
async def ensure_tables() -> None:
    """Ensure DB tables exist for all evolution tests."""
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()
