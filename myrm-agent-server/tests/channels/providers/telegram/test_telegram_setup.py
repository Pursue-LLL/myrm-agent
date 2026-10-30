"""TelegramChannel setup calls: command registration and webhook set-up."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api_core import TelegramApiError
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestTelegramRegisterCommands:
    @pytest.mark.asyncio
    async def test_register_commands_success(self) -> None:
        from app.channels.providers.telegram.helpers import BotCommand

        ch = make_channel()
        ch._commands = [BotCommand(command="help", description="Help")]
        ch._client = MagicMock()
        ch._client.set_my_commands = AsyncMock()

        await ch._register_commands()
        ch._client.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_commands_empty_deletes(self) -> None:
        ch = make_channel()
        ch._commands = []
        ch._client = MagicMock()
        ch._client.delete_my_commands = AsyncMock()

        await ch._register_commands()
        ch._client.delete_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_commands_error_silenced(self) -> None:
        from app.channels.providers.telegram.helpers import BotCommand

        ch = make_channel()
        ch._commands = [BotCommand(command="help", description="Help")]
        ch._client = MagicMock()
        ch._client.set_my_commands = AsyncMock(side_effect=TelegramApiError(400, "Bad Request"))

        await ch._register_commands()


class TestTelegramWebhookSetup:
    @pytest.mark.asyncio
    async def test_setup_webhook(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.set_webhook = AsyncMock()

        await ch._setup_webhook()
        ch._client.set_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_includes_message_reaction_in_allowed_updates(self) -> None:
        from app.channels.providers.telegram.helpers import _ALLOWED_UPDATES

        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.set_webhook = AsyncMock()

        await ch._setup_webhook()
        call_kwargs = ch._client.set_webhook.call_args
        assert call_kwargs.kwargs.get("allowed_updates") is _ALLOWED_UPDATES
        assert "message_reaction" in _ALLOWED_UPDATES

    @pytest.mark.asyncio
    async def test_cleanup_webhook(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.delete_webhook = AsyncMock()

        await ch._cleanup_webhook()
        ch._client.delete_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_webhook_error_silenced(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.delete_webhook = AsyncMock(side_effect=Exception("network"))

        await ch._cleanup_webhook()
