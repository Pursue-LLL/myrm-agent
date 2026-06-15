"""Integration tests for /agent command: full webhook update → channel processing.

Tests the entire handle_webhook_update path without mocking internal logic.
Only external I/O (Bot API calls, DB) is mocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest


@dataclass
class FakeAgentProfile:
    id: str
    display_name: str | None = None


@dataclass
class FakeTopicContext:
    agent_id: str | None = None


class FakeTopicManager:
    """Stub for SqlTopicManager that returns no binding."""

    async def resolve_topic(self, *args, **kwargs) -> FakeTopicContext | None:
        return None


def _build_text_update(text: str, chat_id: int = 123, user_id: int = 456) -> dict:
    """Build a Telegram Update payload with a text message."""
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }


def _build_callback_update(
    data: str, chat_id: int = 123, user_id: int = 456, message_id: int = 99
) -> dict:
    """Build a Telegram Update payload with a callback_query."""
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cbq-001",
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "message": {
                "message_id": message_id,
                "from": {"id": 789, "is_bot": True, "first_name": "Bot"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1700000000,
                "text": "Select an agent:",
            },
            "chat_instance": "inst-1",
            "data": data,
        },
    }


@pytest.fixture
def channel():
    """Create a TelegramChannel with mocked HTTP client."""
    from app.channels.providers.telegram.channel import TelegramChannel

    ch = TelegramChannel(bot_token="123:FAKE", commands=[])
    ch._client = AsyncMock()
    ch._client.answer_callback_query = AsyncMock()
    ch._client.send_message = AsyncMock()
    ch._client.edit_message_text = AsyncMock()
    ch._bot_username = "testbot"
    ch._emitted_messages: list = []

    async def _capture_emit(msg, raw=None):
        ch._emitted_messages.append(msg)

    ch._buffer_or_emit = _capture_emit
    return ch


class TestAgentCommandWebhookIntegration:
    """Full /agent command flow via handle_webhook_update."""

    @pytest.mark.asyncio
    async def test_agent_command_sends_picker_and_suppresses(self, channel):
        """Webhook with /agent text → picker sent, no message emitted."""
        update = _build_text_update("/agent")

        agents = [
            FakeAgentProfile(id="agent-1", display_name="Agent One"),
            FakeAgentProfile(id="agent-2", display_name="Agent Two"),
        ]
        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 2),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=FakeTopicManager(),
            ),
        ):
            await channel.handle_webhook_update(update)

        assert len(channel._emitted_messages) == 0
        channel._client.send_message.assert_awaited_once()

        call_args = channel._client.send_message.call_args
        assert call_args[0][0] == "123"
        reply_markup = call_args.kwargs.get("reply_markup")
        assert reply_markup is not None
        keyboard = reply_markup["inline_keyboard"]
        assert len(keyboard) == 2
        assert keyboard[0][0]["callback_data"] == "ag:agent-1"
        assert keyboard[1][0]["callback_data"] == "ag:agent-2"

    @pytest.mark.asyncio
    async def test_ag_callback_edits_and_emits_bind(self, channel):
        """Webhook with ag: callback → editMessage + emit /bind."""
        update = _build_callback_update("ag:my-agent", message_id=42)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=FakeAgentProfile(id="my-agent", display_name="My Agent"),
        ):
            await channel.handle_webhook_update(update)

        channel._client.edit_message_text.assert_awaited_once()
        call_args = channel._client.edit_message_text.call_args
        assert call_args[0][0] == "123"
        assert call_args[0][1] == 42
        assert "My Agent" in call_args[0][2]
        assert call_args.kwargs.get("reply_markup") == {"inline_keyboard": []}

        assert len(channel._emitted_messages) == 1
        emitted = channel._emitted_messages[0]
        assert emitted.content == "/bind my-agent"

    @pytest.mark.asyncio
    async def test_ag_callback_answers_query(self, channel):
        """Verify answerCallbackQuery is scheduled for ag: callbacks."""
        import asyncio

        update = _build_callback_update("ag:x")

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=FakeAgentProfile(id="x", display_name="X"),
        ):
            await channel.handle_webhook_update(update)
            await asyncio.sleep(0)

        channel._client.answer_callback_query.assert_awaited_once_with("cbq-001")

    @pytest.mark.asyncio
    async def test_normal_message_emits_normally(self, channel):
        """Non-command messages pass through to emit."""
        update = _build_text_update("Hello world")
        await channel.handle_webhook_update(update)

        assert len(channel._emitted_messages) == 1
        assert channel._emitted_messages[0].content == "Hello world"
        channel._client.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_agent_command_with_bot_suffix(self, channel):
        """Webhook with /agent@testbot → same picker behavior."""
        update = _build_text_update("/agent@testbot")

        agents = [FakeAgentProfile(id="a1", display_name="A")]
        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 1),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=FakeTopicManager(),
            ),
        ):
            await channel.handle_webhook_update(update)

        assert len(channel._emitted_messages) == 0
        channel._client.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_picker_marks_current_agent(self, channel):
        """Picker should show ✅ prefix on currently bound agent."""
        update = _build_text_update("/agent")

        agents = [
            FakeAgentProfile(id="active-agent", display_name="Active"),
            FakeAgentProfile(id="other-agent", display_name="Other"),
        ]

        class BoundTopicManager(FakeTopicManager):
            async def resolve_topic(self, *args, **kwargs):
                return FakeTopicContext(agent_id="active-agent")

        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 2),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=BoundTopicManager(),
            ),
        ):
            await channel.handle_webhook_update(update)

        call_args = channel._client.send_message.call_args
        keyboard = call_args.kwargs["reply_markup"]["inline_keyboard"]
        assert keyboard[0][0]["text"].startswith("✅")
        assert not keyboard[1][0]["text"].startswith("✅")

    @pytest.mark.asyncio
    async def test_agent_command_with_trailing_space_still_matches(self, channel):
        """'/agent ' with trailing space → still triggers picker."""
        update = _build_text_update("/agent ")

        agents = [FakeAgentProfile(id="a1", display_name="A")]
        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 1),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=FakeTopicManager(),
            ),
        ):
            await channel.handle_webhook_update(update)

        assert len(channel._emitted_messages) == 0
        channel._client.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_agent_command_with_args_passes_through(self, channel):
        """'/agent help' should NOT trigger picker — only bare /agent."""
        update = _build_text_update("/agent help")
        await channel.handle_webhook_update(update)

        assert len(channel._emitted_messages) == 1
        assert channel._emitted_messages[0].content == "/agent help"

    @pytest.mark.asyncio
    async def test_ag_callback_edit_failure_still_emits_bind(self, channel):
        """If editMessageText fails, /bind still emitted."""
        update = _build_callback_update("ag:fail-agent", message_id=55)

        channel._client.edit_message_text.side_effect = RuntimeError("Telegram 403")

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=FakeAgentProfile(id="fail-agent", display_name="Fail"),
        ):
            await channel.handle_webhook_update(update)

        assert len(channel._emitted_messages) == 1
        assert channel._emitted_messages[0].content == "/bind fail-agent"

    @pytest.mark.asyncio
    async def test_ag_callback_agent_not_found_uses_id_as_name(self, channel):
        """If get_agent_by_id returns None, use raw agent_id in confirmation."""
        update = _build_callback_update("ag:unknown-id", message_id=60)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await channel.handle_webhook_update(update)

        call_args = channel._client.edit_message_text.call_args
        assert "unknown-id" in call_args[0][2]
        assert len(channel._emitted_messages) == 1
        assert channel._emitted_messages[0].content == "/bind unknown-id"

    @pytest.mark.asyncio
    async def test_picker_passes_thread_id_to_message(self, channel):
        """Picker message should include message_thread_id for Forum Topics."""
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 456, "is_bot": False, "first_name": "Test"},
                "chat": {"id": 123, "type": "supergroup"},
                "date": 1700000000,
                "text": "/agent",
                "message_thread_id": 42,
                "is_topic_message": True,
            },
        }

        agents = [FakeAgentProfile(id="a1", display_name="A")]
        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 1),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=FakeTopicManager(),
            ),
        ):
            await channel.handle_webhook_update(update)

        call_kwargs = channel._client.send_message.call_args.kwargs
        assert call_kwargs.get("message_thread_id") == 42
