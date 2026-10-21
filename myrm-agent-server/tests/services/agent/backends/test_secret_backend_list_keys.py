"""Tests for DatabaseSecretBackend.list_secret_keys (no-decrypt key listing).

Validates that key listing queries only the key column and never touches
ciphertext, so a corrupt stored value cannot raise during a config check.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import Agent, AgentSecret
from app.services.agent.backends.secret_backend import DatabaseSecretBackend

AGENT_ID = "secret-list-test-agent"


@pytest.fixture(autouse=True)
async def _seeded_agent() -> None:
    async with get_session() as db:
        await db.execute(delete(AgentSecret).where(AgentSecret.agent_id == AGENT_ID))
        await db.execute(delete(Agent).where(Agent.id == AGENT_ID))
        db.add(Agent(id=AGENT_ID, name="secret-list-test-agent"))
        await db.commit()
    yield
    async with get_session() as db:
        await db.execute(delete(AgentSecret).where(AgentSecret.agent_id == AGENT_ID))
        await db.execute(delete(Agent).where(Agent.id == AGENT_ID))
        await db.commit()


@pytest.mark.asyncio
async def test_list_secret_keys_returns_saved_keys() -> None:
    backend = DatabaseSecretBackend(master_key="test-master-key")
    await backend.save_secret(AGENT_ID, "API_KEY", "value-a", description="a")
    await backend.save_secret(AGENT_ID, "REGION", "value-b", description="b")

    assert sorted(await backend.list_secret_keys(AGENT_ID)) == ["API_KEY", "REGION"]


@pytest.mark.asyncio
async def test_list_secret_keys_empty_for_unknown_agent() -> None:
    backend = DatabaseSecretBackend(master_key="test-master-key")
    assert await backend.list_secret_keys("no-such-agent") == []
