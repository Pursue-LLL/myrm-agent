"""Tests for rate limiting."""

from __future__ import annotations

import time

from app.channels.core.rate_limit import (
    DEFAULT_RATE_LIMIT,
    DISABLED_RATE_LIMIT,
    STRICT_RATE_LIMIT,
    RateLimitConfig,
    RateLimiter,
)
from app.channels.types import InboundMessage


def _msg(sender_id: str = "user1", chat_id: str = "chat1") -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id=sender_id,
        content="test",
        chat_id=chat_id,
    )


class TestRateLimitConfig:
    def test_disabled_config(self) -> None:
        assert DISABLED_RATE_LIMIT.enabled is False

    def test_default_config(self) -> None:
        assert DEFAULT_RATE_LIMIT.enabled is True
        assert DEFAULT_RATE_LIMIT.max_requests == 10
        assert DEFAULT_RATE_LIMIT.window_seconds == 60.0
        assert DEFAULT_RATE_LIMIT.scope == "sender"

    def test_strict_config(self) -> None:
        assert STRICT_RATE_LIMIT.enabled is True
        assert STRICT_RATE_LIMIT.max_requests == 5


import pytest  # noqa: E402


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_disabled_limiter_allows_all(self) -> None:
        limiter = RateLimiter(DISABLED_RATE_LIMIT)
        for _ in range(100):
            assert await limiter.check_and_update(_msg()) is True

    @pytest.mark.asyncio
    async def test_sender_scope_limits_per_sender(self) -> None:
        config = RateLimitConfig(max_requests=3, window_seconds=1.0, scope="sender")
        limiter = RateLimiter(config)

        assert await limiter.check_and_update(_msg("user1", "chat1")) is True
        assert await limiter.check_and_update(_msg("user1", "chat1")) is True
        assert await limiter.check_and_update(_msg("user1", "chat1")) is True
        assert await limiter.check_and_update(_msg("user1", "chat1")) is False

        assert await limiter.check_and_update(_msg("user2", "chat1")) is True

    @pytest.mark.asyncio
    async def test_chat_scope_limits_per_chat(self) -> None:
        config = RateLimitConfig(max_requests=3, window_seconds=1.0, scope="chat")
        limiter = RateLimiter(config)

        assert await limiter.check_and_update(_msg("user1", "chat1")) is True
        assert await limiter.check_and_update(_msg("user2", "chat1")) is True
        assert await limiter.check_and_update(_msg("user3", "chat1")) is True
        assert await limiter.check_and_update(_msg("user4", "chat1")) is False

        assert await limiter.check_and_update(_msg("user1", "chat2")) is True

    @pytest.mark.asyncio
    async def test_global_scope_limits_all(self) -> None:
        config = RateLimitConfig(max_requests=3, window_seconds=1.0, scope="global")
        limiter = RateLimiter(config)

        assert await limiter.check_and_update(_msg("user1", "chat1")) is True
        assert await limiter.check_and_update(_msg("user2", "chat2")) is True
        assert await limiter.check_and_update(_msg("user3", "chat3")) is True
        assert await limiter.check_and_update(_msg("user4", "chat4")) is False

    @pytest.mark.asyncio
    async def test_sliding_window_expires_old_requests(self) -> None:
        config = RateLimitConfig(max_requests=2, window_seconds=0.1, scope="sender")
        limiter = RateLimiter(config)

        assert await limiter.check_and_update(_msg()) is True
        assert await limiter.check_and_update(_msg()) is True
        assert await limiter.check_and_update(_msg()) is False

        time.sleep(0.15)

        assert await limiter.check_and_update(_msg()) is True
        assert await limiter.check_and_update(_msg()) is True
        assert await limiter.check_and_update(_msg()) is False

    @pytest.mark.asyncio
    async def test_reset_clears_state(self) -> None:
        config = RateLimitConfig(max_requests=2, window_seconds=1.0, scope="sender")
        limiter = RateLimiter(config)

        assert await limiter.check_and_update(_msg()) is True
        assert await limiter.check_and_update(_msg()) is True
        assert await limiter.check_and_update(_msg()) is False

        limiter.reset("user1")

        assert await limiter.check_and_update(_msg()) is True

    @pytest.mark.asyncio
    async def test_reset_all_clears_all_state(self) -> None:
        config = RateLimitConfig(max_requests=1, window_seconds=1.0, scope="sender")
        limiter = RateLimiter(config)

        assert await limiter.check_and_update(_msg("user1")) is True
        assert await limiter.check_and_update(_msg("user2")) is True
        assert await limiter.check_and_update(_msg("user1")) is False
        assert await limiter.check_and_update(_msg("user2")) is False

        limiter.reset()

        assert await limiter.check_and_update(_msg("user1")) is True
        assert await limiter.check_and_update(_msg("user2")) is True
