"""E2E test for ChannelStatusProvider — real DB, no mocks."""

from __future__ import annotations

import uuid

import pytest

from app.core.channel_bridge.status_handler import ChannelStatusProvider
from app.database.connection import get_session
from app.database.models.agent import Agent
from app.database.models.chat import Chat


@pytest.fixture
async def _seed_chat() -> str:
    """Insert a Chat row with a known channel_session_key and return it."""
    chat_id = f"test_{uuid.uuid4().hex[:12]}"
    session_key = f"telegram:dm:{chat_id}"

    async with get_session() as db:
        chat = Chat(
            id=chat_id,
            title="Status E2E Test Chat",
            source="channel",
            channel_session_key=session_key,
            total_tokens=42_000,
            total_calls=5,
            total_usd=0.12,
        )
        db.add(chat)
        await db.commit()

    return chat_id


@pytest.fixture
async def _seed_chat_with_agent() -> tuple[str, str]:
    """Insert Chat + Agent with model_selection, return (chat_id, agent_id)."""
    agent_id = f"agent_{uuid.uuid4().hex[:8]}"
    chat_id = f"test_{uuid.uuid4().hex[:12]}"
    session_key = f"whatsapp:dm:{chat_id}"

    async with get_session() as db:
        agent = Agent(
            id=agent_id,
            name="Test Agent",
            model_selection={"model": "claude-4-sonnet"},
        )
        db.add(agent)

        chat = Chat(
            id=chat_id,
            title="Chat With Agent",
            source="channel",
            channel_session_key=session_key,
            agent_id=agent_id,
            total_tokens=8_000,
            total_calls=2,
            total_usd=0.05,
        )
        db.add(chat)
        await db.commit()

    return chat_id, agent_id


class TestChannelStatusProviderE2E:
    """Integration tests for ChannelStatusProvider with real DB."""

    @pytest.mark.asyncio
    async def test_returns_session_status_for_existing_chat(self, _seed_chat: str) -> None:
        provider = ChannelStatusProvider()
        status = await provider.get_session_status("telegram", _seed_chat)

        assert status is not None
        assert status.session_id == _seed_chat
        assert status.title == "Status E2E Test Chat"
        assert status.total_tokens == 42_000
        assert status.total_usd == 0.12
        assert status.total_calls == 5
        assert status.created_at is not None
        assert status.last_activity is not None

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_session(self) -> None:
        provider = ChannelStatusProvider()
        status = await provider.get_session_status("telegram", "nonexistent_peer_999")

        assert status is None

    @pytest.mark.asyncio
    async def test_exact_match_no_partial_collision(self, _seed_chat: str) -> None:
        """Ensure key='telegram:abc' does NOT match key='telegram:abcdef'."""
        provider = ChannelStatusProvider()

        partial_id = _seed_chat[:6]
        status = await provider.get_session_status("telegram", partial_id)

        assert status is None

    @pytest.mark.asyncio
    async def test_timestamps_format(self, _seed_chat: str) -> None:
        provider = ChannelStatusProvider()
        status = await provider.get_session_status("telegram", _seed_chat)

        assert status is not None
        assert status.created_at is not None
        parts = status.created_at.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4

    @pytest.mark.asyncio
    async def test_model_name_none_without_agent(self, _seed_chat: str) -> None:
        provider = ChannelStatusProvider()
        status = await provider.get_session_status("telegram", _seed_chat)

        assert status is not None
        assert status.model_name is None

    @pytest.mark.asyncio
    async def test_resolve_model_name_none_agent_id(self) -> None:
        async with get_session() as db:
            result = await ChannelStatusProvider._resolve_model_name(db, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_model_name_nonexistent_agent(self) -> None:
        async with get_session() as db:
            result = await ChannelStatusProvider._resolve_model_name(db, "nonexistent_agent_id_xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_model_name_with_real_agent(self, _seed_chat_with_agent: tuple[str, str]) -> None:
        """Verify _resolve_model_name returns model from Agent.model_selection."""
        _, agent_id = _seed_chat_with_agent
        async with get_session() as db:
            result = await ChannelStatusProvider._resolve_model_name(db, agent_id)
        assert result == "claude-4-sonnet"

    @pytest.mark.asyncio
    async def test_chat_with_agent_returns_metadata(self, _seed_chat_with_agent: tuple[str, str]) -> None:
        """Verify get_session_status returns core fields for chat with agent."""
        chat_id, _ = _seed_chat_with_agent
        provider = ChannelStatusProvider()
        status = await provider.get_session_status("whatsapp", chat_id)
        assert status is not None
        assert status.session_id == chat_id
        assert status.title == "Chat With Agent"
        assert status.total_tokens == 8_000
        assert status.total_usd == 0.05
        assert status.total_calls == 2
