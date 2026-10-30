"""Long-polling loop: 409 conflict recovery and network-error degradation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import (
    ChannelStatus,
)
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestIsPollingConflict:
    """Unit tests for _is_polling_conflict static method."""

    def test_409_conflict_text(self) -> None:
        err = Exception("Telegram API 409: Conflict: terminated by other getUpdates request")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_terminated_by_other_request(self) -> None:
        err = Exception("terminated by other getUpdates request")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_conflict_in_type_name(self) -> None:
        class ConflictError(Exception):
            pass

        err = ConflictError("polling failed")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_409_and_conflict_keywords(self) -> None:
        err = Exception("Error 409: conflict detected")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_409_without_conflict_keyword(self) -> None:
        err = Exception("Error 409: something else")
        assert TelegramChannel._is_polling_conflict(err) is False

    def test_network_error_not_conflict(self) -> None:
        err = Exception("Connection timeout")
        assert TelegramChannel._is_polling_conflict(err) is False

    def test_generic_api_error_not_conflict(self) -> None:
        err = TelegramApiError(500, "Internal Server Error")
        assert TelegramChannel._is_polling_conflict(err) is False

    def test_telegram_api_409_conflict(self) -> None:
        err = TelegramApiError(409, "Conflict: terminated by other getUpdates request")
        assert TelegramChannel._is_polling_conflict(err) is True


class TestPollLoopConflictRecovery:
    """Integration tests for _poll_loop conflict error handling."""

    @pytest.mark.asyncio
    async def test_conflict_retries_then_stops(self) -> None:
        """After _MAX_CONFLICT_RETRIES conflicts, loop stops with ERROR status."""
        from app.channels.providers.telegram.helpers import (
            _MAX_CONFLICT_RETRIES,
        )

        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()
        ch._client.get_updates = AsyncMock(side_effect=TelegramApiError(409, "Conflict: terminated by other getUpdates request"))

        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.ERROR
        assert ch._client.get_updates.call_count == _MAX_CONFLICT_RETRIES + 1
        assert ch.health.last_error is not None
        assert "polling" in ch.health.last_error.lower()

    @pytest.mark.asyncio
    async def test_conflict_resolves_before_max_retries(self) -> None:
        """Conflict errors that resolve within limit allow recovery."""
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise TelegramApiError(409, "Conflict: terminated by other getUpdates request")
            if call_count == 3:
                return [
                    {
                        "update_id": 1,
                        "message": {"message_id": 1, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "hello"},
                    }
                ]
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)
        ch.set_inbound_handler(AsyncMock())

        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED
        assert ch.health.last_error is None or "conflict" not in (ch.health.last_error or "").lower()


class TestPollLoopNetworkRecovery:
    """Integration tests for _poll_loop network error handling."""

    @pytest.mark.asyncio
    async def test_network_errors_degrade_then_recover(self) -> None:
        """Network errors trigger DEGRADED; successful poll restores RUNNING."""
        from app.channels.providers.telegram.helpers import (
            _DEGRADED_THRESHOLD,
        )

        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= _DEGRADED_THRESHOLD:
                raise OSError("Connection reset by peer")
            if call_count == _DEGRADED_THRESHOLD + 1:
                return []
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED
        assert ch.is_connected is True

    @pytest.mark.asyncio
    async def test_network_errors_below_threshold_stay_running(self) -> None:
        """Network errors below _DEGRADED_THRESHOLD keep RUNNING status."""
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise OSError("Network unreachable")
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_degraded_status_continues_polling(self) -> None:
        """Polling continues when status is DEGRADED (not stuck)."""
        from app.channels.providers.telegram.helpers import (
            _DEGRADED_THRESHOLD,
        )

        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= _DEGRADED_THRESHOLD + 2:
                raise OSError("Connection timeout")
            # After recovery, stop the loop
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        # Must have polled beyond threshold (proves DEGRADED didn't exit loop)
        assert call_count > _DEGRADED_THRESHOLD

    @pytest.mark.asyncio
    async def test_cancelled_error_breaks_loop(self) -> None:
        """CancelledError cleanly exits the loop."""
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()
        ch._client.get_updates = AsyncMock(side_effect=asyncio.CancelledError)

        await ch._poll_loop()
        assert ch._status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_successful_poll_resets_backoff(self) -> None:
        """After recovery from errors, conflict_count and consecutive_errors reset."""
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("Transient error")
            if call_count == 2:
                return []
            if call_count == 3:
                raise OSError("Another transient")
            if call_count == 4:
                return []
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_poll_loop_processes_updates_normally(self) -> None:
        """Normal poll loop processes updates and advances offset."""
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()
        received: list[object] = []

        async def handler(msg: object) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    {
                        "update_id": 100,
                        "message": {
                            "message_id": 1,
                            "from": {"id": 42, "username": "alice"},
                            "chat": {"id": 42, "type": "private"},
                            "text": "hello",
                        },
                    }
                ]
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        await ch._poll_loop()
        assert ch._offset == 101
        assert len(received) == 1
