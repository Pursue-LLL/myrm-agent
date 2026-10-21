"""Tests for DatabaseSecretBackend external vault reference resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import Agent, AgentSecret
from app.services.agent.backends.secret_backend import DatabaseSecretBackend

AGENT_ID = "external-secret-test-agent"


@pytest.fixture(autouse=True)
async def _seeded_agent() -> None:
    async with get_session() as db:
        await db.execute(delete(AgentSecret).where(AgentSecret.agent_id == AGENT_ID))
        await db.execute(delete(Agent).where(Agent.id == AGENT_ID))
        db.add(Agent(id=AGENT_ID, name="external-secret-test-agent"))
        await db.commit()
    yield
    async with get_session() as db:
        await db.execute(delete(AgentSecret).where(AgentSecret.agent_id == AGENT_ID))
        await db.execute(delete(Agent).where(Agent.id == AGENT_ID))
        await db.commit()


@pytest.mark.asyncio
async def test_get_secret_resolves_external_reference() -> None:
    """Validate that op:// or bw:// references are dynamically resolved in get_secret."""
    backend = DatabaseSecretBackend(master_key="test-master-key")
    await backend.save_secret(AGENT_ID, "GITHUB_TOKEN", "op://Personal/GitHub/token")

    with patch(
        "app.services.agent.backends.secret_backend.resolve_external_secret",
        return_value="ghp_live_token_resolved_xyz",
    ) as mock_resolve:
        val = await backend.get_secret(AGENT_ID, "GITHUB_TOKEN")
        assert val == "ghp_live_token_resolved_xyz"
        mock_resolve.assert_called_once_with("op://Personal/GitHub/token")


@pytest.mark.asyncio
async def test_get_secret_plain_value_unaltered() -> None:
    """Validate that regular plaintext tokens pass through without invoking resolver."""
    backend = DatabaseSecretBackend(master_key="test-master-key")
    await backend.save_secret(AGENT_ID, "PLAIN_KEY", "sk-regular-plain-token-123")

    with patch("app.services.agent.backends.secret_backend.resolve_external_secret") as mock_resolve:
        val = await backend.get_secret(AGENT_ID, "PLAIN_KEY")
        assert val == "sk-regular-plain-token-123"
        mock_resolve.assert_not_called()


@pytest.mark.asyncio
async def test_get_all_secrets_resolves_mixed_values() -> None:
    """Validate that get_all_secrets resolves external references while preserving plain keys."""
    backend = DatabaseSecretBackend(master_key="test-master-key")
    await backend.save_secret(AGENT_ID, "PLAIN_KEY", "plain-val")
    await backend.save_secret(AGENT_ID, "VAULT_KEY", "bw://anthropic-key")

    with patch(
        "app.services.agent.backends.secret_backend.resolve_external_secret",
        return_value="resolved-anthropic-key",
    ) as mock_resolve:
        all_secrets = await backend.get_all_secrets(AGENT_ID)
        assert all_secrets["PLAIN_KEY"] == "plain-val"
        assert all_secrets["VAULT_KEY"] == "resolved-anthropic-key"
        mock_resolve.assert_called_once_with("bw://anthropic-key")


@pytest.mark.asyncio
async def test_get_secret_graceful_fallback_on_resolution_error() -> None:
    """Validate graceful degradation if the external resolver times out or fails."""
    backend = DatabaseSecretBackend(master_key="test-master-key")
    await backend.save_secret(AGENT_ID, "FAIL_KEY", "op://Broken/Vault/key")

    with patch(
        "app.services.agent.backends.secret_backend.resolve_external_secret",
        side_effect=RuntimeError("CLI unreachable"),
    ):
        val = await backend.get_secret(AGENT_ID, "FAIL_KEY")
        assert val == "op://Broken/Vault/key"
