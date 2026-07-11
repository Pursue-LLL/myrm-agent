"""Tests for WeChatILinkChannel typing ticket TTL management."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.providers.wechat.ilink_channel import (
    WeChatILinkChannel,
    _TYPING_TICKET_TTL,
)


def _make_channel() -> WeChatILinkChannel:
    ch = WeChatILinkChannel(
        bot_token="test-token",
        ilink_bot_id="test-bot-id",
    )
    ch._client.get_config = AsyncMock(return_value={"typing_ticket": "ticket-abc"})
    ch._client.send_typing = AsyncMock()
    return ch


class TestEnsureTypingTicket:
    @pytest.mark.asyncio
    async def test_fetches_ticket_on_first_call(self) -> None:
        ch = _make_channel()
        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket == "ticket-abc"
        assert "user1" in ch._typing_tickets
        ch._client.get_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_cached_ticket_within_ttl(self) -> None:
        ch = _make_channel()
        await ch._ensure_typing_ticket("user1")
        ch._client.get_config.reset_mock()

        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket == "ticket-abc"
        ch._client.get_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refreshes_ticket_after_ttl_expired(self) -> None:
        ch = _make_channel()
        await ch._ensure_typing_ticket("user1")

        expired_time = time.monotonic() - _TYPING_TICKET_TTL - 10
        ch._typing_tickets["user1"] = ("ticket-abc", expired_time)

        ch._client.get_config = AsyncMock(return_value={"typing_ticket": "ticket-new"})
        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket == "ticket-new"
        ch._client.get_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_get_config_failure(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(side_effect=RuntimeError("network"))
        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_ticket(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(return_value={"typing_ticket": ""})
        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket is None

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_ticket_key(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(return_value={})
        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket is None

    @pytest.mark.asyncio
    async def test_uses_monotonic_clock(self) -> None:
        ch = _make_channel()
        with patch("app.channels.providers.wechat.ilink_channel.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            await ch._ensure_typing_ticket("user1")
            assert ch._typing_tickets["user1"][1] == 1000.0

            mock_time.monotonic.return_value = 1000.0 + _TYPING_TICKET_TTL - 1
            ch._client.get_config.reset_mock()
            await ch._ensure_typing_ticket("user1")
            ch._client.get_config.assert_not_awaited()

            mock_time.monotonic.return_value = 1000.0 + _TYPING_TICKET_TTL + 1
            ch._client.get_config = AsyncMock(
                return_value={"typing_ticket": "ticket-refreshed"}
            )
            ticket = await ch._ensure_typing_ticket("user1")
            assert ticket == "ticket-refreshed"
            ch._client.get_config.assert_awaited_once()


class TestStartTypingWithTTL:
    @pytest.mark.asyncio
    async def test_sends_typing_with_valid_ticket(self) -> None:
        ch = _make_channel()
        await ch.start_typing("user1")
        ch._client.send_typing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_when_no_ticket(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(side_effect=RuntimeError("fail"))
        await ch.start_typing("user1")
        ch._client.send_typing.assert_not_awaited()


class TestStopTypingWithTTL:
    @pytest.mark.asyncio
    async def test_sends_cancel_with_valid_ticket(self) -> None:
        ch = _make_channel()
        await ch.start_typing("user1")
        ch._client.send_typing.reset_mock()
        await ch.stop_typing("user1")
        ch._client.send_typing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refreshes_expired_ticket_for_stop(self) -> None:
        """stop_typing must refresh expired ticket to deliver cancel signal."""
        ch = _make_channel()
        await ch.start_typing("user1")

        expired_time = time.monotonic() - _TYPING_TICKET_TTL - 10
        ch._typing_tickets["user1"] = ("ticket-old", expired_time)
        ch._client.get_config = AsyncMock(
            return_value={"typing_ticket": "ticket-for-stop"}
        )
        ch._client.send_typing.reset_mock()

        await ch.stop_typing("user1")
        ch._client.get_config.assert_awaited_once()
        ch._client.send_typing.assert_awaited_once()


class TestMultiChatIdIsolation:
    """Verify ticket caches for different chat_ids are fully independent."""

    @pytest.mark.asyncio
    async def test_separate_chat_ids_have_independent_tickets(self) -> None:
        ch = _make_channel()
        call_count = 0

        async def _get_config_side_effect(
            ilink_user_id: str, context_token: str | None = None
        ) -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"typing_ticket": f"ticket-{ilink_user_id}"}

        ch._client.get_config = AsyncMock(side_effect=_get_config_side_effect)

        t1 = await ch._ensure_typing_ticket("user-a")
        t2 = await ch._ensure_typing_ticket("user-b")
        assert t1 == "ticket-user-a"
        assert t2 == "ticket-user-b"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_expiry_of_one_does_not_affect_other(self) -> None:
        ch = _make_channel()
        now = time.monotonic()
        ch._typing_tickets["user-a"] = ("ticket-a", now)
        ch._typing_tickets["user-b"] = ("ticket-b", now - _TYPING_TICKET_TTL - 10)

        t_a = await ch._ensure_typing_ticket("user-a")
        assert t_a == "ticket-a"
        ch._client.get_config.assert_not_awaited()

        ch._client.get_config = AsyncMock(return_value={"typing_ticket": "ticket-b-new"})
        t_b = await ch._ensure_typing_ticket("user-b")
        assert t_b == "ticket-b-new"
        ch._client.get_config.assert_awaited_once()


class TestSendTypingErrorHandling:
    """Verify send_typing exceptions are caught and don't propagate."""

    @pytest.mark.asyncio
    async def test_start_typing_send_failure_caught(self) -> None:
        ch = _make_channel()
        ch._client.send_typing = AsyncMock(side_effect=RuntimeError("network error"))
        await ch.start_typing("user1")
        ch._client.send_typing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_typing_send_failure_caught(self) -> None:
        ch = _make_channel()
        ch._typing_tickets["user1"] = ("ticket-abc", time.monotonic())
        ch._client.send_typing = AsyncMock(side_effect=ConnectionError("timeout"))
        await ch.stop_typing("user1")
        ch._client.send_typing.assert_awaited_once()


class TestContextTokenPassthrough:
    """Verify _context_tokens are correctly passed to get_config."""

    @pytest.mark.asyncio
    async def test_passes_stored_context_token(self) -> None:
        ch = _make_channel()
        ch._context_tokens["user1"] = "ctx-token-123"
        await ch._ensure_typing_ticket("user1")
        ch._client.get_config.assert_awaited_once_with("user1", "ctx-token-123")

    @pytest.mark.asyncio
    async def test_passes_none_when_no_context_token(self) -> None:
        ch = _make_channel()
        await ch._ensure_typing_ticket("user1")
        ch._client.get_config.assert_awaited_once_with("user1", None)


class TestEdgeCaseTicketValues:
    """Non-string and edge-case typing_ticket values from get_config."""

    @pytest.mark.asyncio
    async def test_integer_ticket_returns_none(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(return_value={"typing_ticket": 12345})
        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket is None
        assert "user1" not in ch._typing_tickets

    @pytest.mark.asyncio
    async def test_none_ticket_returns_none(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(return_value={"typing_ticket": None})
        ticket = await ch._ensure_typing_ticket("user1")
        assert ticket is None

    @pytest.mark.asyncio
    async def test_ttl_boundary_exact_not_expired(self) -> None:
        """Ticket at exactly TTL - epsilon is still valid."""
        ch = _make_channel()
        with patch("app.channels.providers.wechat.ilink_channel.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            await ch._ensure_typing_ticket("user1")
            ch._client.get_config.reset_mock()

            mock_time.monotonic.return_value = 1000.0 + _TYPING_TICKET_TTL - 0.001
            ticket = await ch._ensure_typing_ticket("user1")
            assert ticket == "ticket-abc"
            ch._client.get_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ttl_boundary_exact_expired(self) -> None:
        """Ticket at exactly TTL is expired and triggers refresh."""
        ch = _make_channel()
        with patch("app.channels.providers.wechat.ilink_channel.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            await ch._ensure_typing_ticket("user1")

            mock_time.monotonic.return_value = 1000.0 + _TYPING_TICKET_TTL
            ch._client.get_config = AsyncMock(
                return_value={"typing_ticket": "ticket-boundary"}
            )
            ticket = await ch._ensure_typing_ticket("user1")
            assert ticket == "ticket-boundary"
            ch._client.get_config.assert_awaited_once()


class TestFullLifecycle:
    """End-to-end lifecycle: start → keepalive → stop → restart."""

    @pytest.mark.asyncio
    async def test_start_stop_restart_lifecycle(self) -> None:
        ch = _make_channel()
        await ch.start_typing("user1")
        assert ch._client.send_typing.await_count == 1

        await ch.stop_typing("user1")
        assert ch._client.send_typing.await_count == 2

        ch._client.send_typing.reset_mock()
        await ch.start_typing("user1")
        ch._client.send_typing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_without_prior_start_attempts_get_config(self) -> None:
        """stop_typing on cold channel tries to fetch ticket (best-effort cancel)."""
        ch = _make_channel()
        assert "user1" not in ch._typing_tickets
        await ch.stop_typing("user1")
        ch._client.get_config.assert_awaited_once()
        ch._client.send_typing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_ticket_refreshed_during_keepalive_cycle(self) -> None:
        """Simulates keepalive loop calling start_typing after TTL expiry."""
        ch = _make_channel()
        await ch.start_typing("user1")

        expired_time = time.monotonic() - _TYPING_TICKET_TTL - 10
        ch._typing_tickets["user1"] = ("ticket-old", expired_time)
        ch._client.get_config = AsyncMock(
            return_value={"typing_ticket": "ticket-refreshed"}
        )
        ch._client.send_typing.reset_mock()

        await ch.start_typing("user1")
        ch._client.get_config.assert_awaited_once()
        ch._client.send_typing.assert_awaited_once()
        assert ch._typing_tickets["user1"][0] == "ticket-refreshed"
