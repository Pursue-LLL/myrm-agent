"""Unit tests for /agent command handling in TelegramChannel.

Tests cover:
- /agent text command → picker sent + message suppressed
- /agent@botname variant
- ag: callback → editMessageText + /bind conversion
- Edge cases: empty agent_id, missing origin_message_id
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types.messages import InboundMessage


def _make_msg(
    content: str = "",
    metadata: dict[str, object] | None = None,
    chat_id: str | None = "12345",
    sender_id: str = "user1",
    thread_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        metadata=metadata or {},
        thread_id=thread_id,
    )


@dataclass
class FakeAgentProfile:
    id: str
    display_name: str | None = None


class TestHandleAgentCommand:
    """Test _handle_agent_command dispatch logic."""

    @pytest.fixture
    def channel(self):
        """Create a minimal TelegramChannel-like object with mocked dependencies."""
        from app.channels.providers.telegram.channel import TelegramChannel

        with patch.object(TelegramChannel, "__init__", lambda self, **kw: None):
            ch = TelegramChannel.__new__(TelegramChannel)
            ch._client = AsyncMock()
            ch._bot_username = "testbot"
            ch._send_agent_picker = AsyncMock()
            return ch

    @pytest.mark.asyncio
    async def test_agent_command_sends_picker(self, channel):
        msg = _make_msg(content="/agent")
        result = await channel._handle_agent_command(msg)
        assert result is None
        channel._send_agent_picker.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    async def test_agent_command_with_bot_suffix(self, channel):
        msg = _make_msg(content="/agent@TestBot")
        result = await channel._handle_agent_command(msg)
        assert result is None
        channel._send_agent_picker.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_agent_command_case_insensitive(self, channel):
        msg = _make_msg(content="/AGENT@TESTBOT")
        result = await channel._handle_agent_command(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_agent_message_passes_through(self, channel):
        msg = _make_msg(content="Hello world")
        result = await channel._handle_agent_command(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_ag_callback_converts_to_bind(self, channel):
        msg = _make_msg(
            content="my-agent-id",
            metadata={"callback_prefix": "ag", "origin_message_id": 999},
        )
        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=FakeAgentProfile(id="my-agent-id", display_name="My Agent"),
        ):
            result = await channel._handle_agent_command(msg)

        assert result is not None
        assert result.content == "/bind my-agent-id"

    @pytest.mark.asyncio
    async def test_ag_callback_edits_picker_message(self, channel):
        msg = _make_msg(
            content="agent-x",
            metadata={"callback_prefix": "ag", "origin_message_id": 42},
        )
        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=FakeAgentProfile(id="agent-x", display_name="Agent X"),
        ):
            await channel._handle_agent_command(msg)

        channel._client.edit_message_text.assert_awaited_once()
        call_args = channel._client.edit_message_text.call_args
        assert call_args[0][0] == "12345"
        assert call_args[0][1] == 42
        assert "Agent X" in call_args[0][2]
        assert call_args.kwargs.get("reply_markup") == {"inline_keyboard": []}

    @pytest.mark.asyncio
    async def test_ag_callback_no_origin_message_skips_edit(self, channel):
        msg = _make_msg(
            content="agent-y",
            metadata={"callback_prefix": "ag", "origin_message_id": None},
        )
        result = await channel._handle_agent_command(msg)
        assert result is not None
        assert result.content == "/bind agent-y"
        channel._client.edit_message_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ag_callback_empty_agent_id_passes_through(self, channel):
        msg = _make_msg(content="", metadata={"callback_prefix": "ag"})
        result = await channel._handle_agent_command(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_picker_failure_still_suppresses(self, channel):
        channel._send_agent_picker.side_effect = RuntimeError("API down")
        msg = _make_msg(content="/agent")
        result = await channel._handle_agent_command(msg)
        assert result is None


class _FakeTopicContext:
    def __init__(self, agent_id: str | None = None):
        self.agent_id = agent_id


class _FakeTopicManager:
    async def resolve_topic(self, *args, **kwargs):
        return None


class TestSendAgentPicker:
    """Test _send_agent_picker inline keyboard construction."""

    @pytest.fixture
    def channel(self):
        from app.channels.providers.telegram.channel import TelegramChannel

        with patch.object(TelegramChannel, "__init__", lambda self, **kw: None):
            ch = TelegramChannel.__new__(TelegramChannel)
            ch._client = AsyncMock()
            return ch

    @pytest.mark.asyncio
    async def test_picker_sends_keyboard(self, channel):
        agents = [
            FakeAgentProfile(id="a1", display_name="Alpha"),
            FakeAgentProfile(id="a2", display_name="Beta"),
        ]
        msg = _make_msg(content="/agent", thread_id="77")

        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 2),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=_FakeTopicManager(),
            ),
        ):
            await channel._send_agent_picker(msg)

        channel._client.send_message.assert_awaited_once()
        call_args = channel._client.send_message.call_args

        assert call_args[0][0] == "12345"
        reply_markup = call_args.kwargs.get("reply_markup")
        assert reply_markup is not None
        keyboard = reply_markup["inline_keyboard"]
        assert len(keyboard) == 2
        assert keyboard[0][0]["callback_data"] == "ag:a1"
        assert keyboard[1][0]["callback_data"] == "ag:a2"

    @pytest.mark.asyncio
    async def test_picker_no_agents_sends_message(self, channel):
        msg = _make_msg(content="/agent")

        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=_FakeTopicManager(),
            ),
        ):
            await channel._send_agent_picker(msg)

        channel._client.send_message.assert_awaited_once()
        args = channel._client.send_message.call_args[0]
        assert "No agents" in args[1] or "未配置" in args[1]

    @pytest.mark.asyncio
    async def test_picker_no_chat_id_returns_early(self, channel):
        msg = _make_msg(content="/agent", chat_id=None, sender_id="")

        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=([FakeAgentProfile(id="x")], 1),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=_FakeTopicManager(),
            ),
        ):
            await channel._send_agent_picker(msg)

        channel._client.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_picker_uses_id_as_fallback_label(self, channel):
        agents = [FakeAgentProfile(id="raw-id", display_name=None)]
        msg = _make_msg(content="/agent")

        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 1),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=_FakeTopicManager(),
            ),
        ):
            await channel._send_agent_picker(msg)

        call_kwargs = channel._client.send_message.call_args.kwargs
        reply_markup = call_kwargs.get("reply_markup")
        assert reply_markup["inline_keyboard"][0][0]["text"] == "raw-id"

    @pytest.mark.asyncio
    async def test_picker_marks_bound_agent_with_checkmark(self, channel):
        agents = [
            FakeAgentProfile(id="a1", display_name="Alpha"),
            FakeAgentProfile(id="a2", display_name="Beta"),
        ]
        msg = _make_msg(content="/agent")

        class _BoundTopicManager:
            async def resolve_topic(self, channel_name, chat_id, thread_id):
                if thread_id is None:
                    return _FakeTopicContext(agent_id="a2")
                return None

        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 2),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=_BoundTopicManager(),
            ),
        ):
            await channel._send_agent_picker(msg)

        call_kwargs = channel._client.send_message.call_args.kwargs
        keyboard = call_kwargs["reply_markup"]["inline_keyboard"]
        assert keyboard[0][0]["text"] == "Alpha"
        assert keyboard[1][0]["text"] == "✅ Beta"

    @pytest.mark.asyncio
    async def test_picker_no_bound_agent_no_checkmark(self, channel):
        agents = [FakeAgentProfile(id="a1", display_name="Alpha")]
        msg = _make_msg(content="/agent")

        with (
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=(agents, 1),
            ),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager",
                return_value=_FakeTopicManager(),
            ),
        ):
            await channel._send_agent_picker(msg)

        call_kwargs = channel._client.send_message.call_args.kwargs
        keyboard = call_kwargs["reply_markup"]["inline_keyboard"]
        assert keyboard[0][0]["text"] == "Alpha"
        assert "✅" not in keyboard[0][0]["text"]
