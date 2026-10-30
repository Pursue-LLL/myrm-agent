"""TelegramChannel contract, lifecycle, health, retry classification and voice download."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
)
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN, ChannelTestBase
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestTelegramChannel(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)


class TestTelegramChannelLifecycle:
    @pytest.mark.asyncio
    async def test_start_success_webhook(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(return_value={"id": 123, "username": "testbot"})
        ch._client.set_webhook = AsyncMock()

        with patch.object(ch, "_register_commands", new_callable=AsyncMock):
            with patch.object(ch, "_setup_webhook", new_callable=AsyncMock):
                await ch.start()

        assert ch._status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_no_token(self) -> None:
        ch = TelegramChannel(bot_token="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_token_verification_fails(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(side_effect=TelegramApiError(401, "Unauthorized"))

        await ch.start()
        assert ch._status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.delete_webhook = AsyncMock()
        ch._poll_task = None

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        ch._client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.verify_token = AsyncMock(return_value=True)

        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_stopped(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.verify_token = AsyncMock(side_effect=Exception("network error"))

        assert await ch.health_check() is False

    def test_should_retry_429(self) -> None:
        ch = make_channel()
        err = TelegramApiError(429, "Too Many Requests", {"retry_after": 10})
        assert ch.should_retry(err) is True

    def test_should_not_retry_401(self) -> None:
        ch = make_channel()
        err = TelegramApiError(401, "Unauthorized")
        assert ch.should_retry(err) is False

    def test_extract_retry_after(self) -> None:
        ch = make_channel()
        err = TelegramApiError(429, "Too Many Requests", {"retry_after": 30})
        assert ch.extract_retry_after(err) == 30.0

    def test_is_webhook_mode(self) -> None:
        ch = TelegramChannel(bot_token="tok", webhook_url="https://example.com/wh")
        assert ch.is_webhook_mode is True

    def test_is_polling_mode(self) -> None:
        ch = TelegramChannel(bot_token="tok")
        assert ch.is_webhook_mode is False

    def test_redact(self) -> None:
        ch = make_channel()
        text = f"Error with token {ch._token}"
        redacted = ch._redact(text)
        assert ch._token not in redacted
        assert "REDACTED" in redacted

    def test_webhook_secret(self) -> None:
        ch = make_channel()
        secret = ch.webhook_secret
        assert len(secret) == 32


class TestTelegramStartPolling:
    @pytest.mark.asyncio
    async def test_start_polling_mode(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(return_value={"id": 123, "username": "testbot"})
        ch._client.delete_my_commands = AsyncMock()
        ch._client.delete_webhook = AsyncMock()

        with patch.object(ch, "_poll_loop", new_callable=AsyncMock):
            await ch.start()
            assert ch._status == ChannelStatus.RUNNING
            assert ch._poll_task is not None
            ch._poll_task.cancel()
            try:
                await ch._poll_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_start_webhook_setup_fails_degrades(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(return_value={"id": 123, "username": "testbot"})
        ch._client.delete_my_commands = AsyncMock()
        ch._client.set_webhook = AsyncMock(side_effect=TelegramApiError(400, "Bad Request"))

        await ch.start()
        assert ch._status == ChannelStatus.DEGRADED


class TestTelegramStopFull:
    @pytest.mark.asyncio
    async def test_stop_flushes_media_groups(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._poll_task = None

        from app.channels.providers.telegram.helpers import _MediaGroupBuffer

        buf = _MediaGroupBuffer()
        buf.messages.append(
            InboundMessage(
                channel="telegram",
                sender_id="42",
                chat_id="42",
                content="grouped",
                message_id="mg1",
            )
        )
        ch._mg_buffers["mg_key"] = buf

        emitted: list[object] = []

        async def _handler(msg: object) -> None:
            emitted.append(msg)

        ch.set_inbound_handler(_handler)

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert len(emitted) == 1

    @pytest.mark.asyncio
    async def test_stop_cancels_poll_task(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._poll_task = asyncio.create_task(_forever())
        await ch.stop()
        assert ch._poll_task is None

    @pytest.mark.asyncio
    async def test_stop_webhook_mode_cleanup(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.delete_webhook = AsyncMock()
        ch._poll_task = None

        await ch.stop()
        ch._client.delete_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_deletes_commands(self) -> None:
        from app.channels.providers.telegram.helpers import BotCommand

        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._commands = [BotCommand(command="help", description="Help")]
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._poll_task = None

        await ch.stop()
        ch._client.delete_my_commands.assert_called_once()


class TestTelegramHealthCheckVerifyFailed:
    @pytest.mark.asyncio
    async def test_health_check_verify_false(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.verify_token = AsyncMock(return_value=False)

        assert await ch.health_check() is False


class TestTelegramDownloadVoice:
    @pytest.mark.asyncio
    async def test_download_voice_message(self) -> None:
        from pathlib import Path

        ch = make_channel()
        ch._client = MagicMock()
        ch._client.download_voice = AsyncMock(return_value=Path("/tmp/voice.ogg"))

        result = await ch.download_voice_message("file_123")
        assert result == Path("/tmp/voice.ogg")
        ch._client.download_voice.assert_called_once_with("file_123")


class TestTelegramRetryMethods:
    def test_should_retry_non_telegram_error_delegates_to_base(self) -> None:
        ch = make_channel()
        result = ch.should_retry(RuntimeError("generic"))
        assert isinstance(result, bool)

    def test_should_retry_403(self) -> None:
        ch = make_channel()
        err = TelegramApiError(403, "Forbidden")
        assert ch.should_retry(err) is False

    def test_extract_retry_after_non_telegram_error(self) -> None:
        ch = make_channel()
        assert ch.extract_retry_after(RuntimeError("generic")) is None

    def test_extract_retry_after_no_param(self) -> None:
        ch = make_channel()
        err = TelegramApiError(429, "Too Many Requests")
        assert ch.extract_retry_after(err) is None
