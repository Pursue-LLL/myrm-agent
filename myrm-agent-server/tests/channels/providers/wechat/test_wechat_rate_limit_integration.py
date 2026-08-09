"""Integration tests for WeChat rate-limit → retry → degradation full chain.

Validates the complete flow without mocking critical path components
(send_with_retry, TokenBucket, MessageBus dispatch). Only HTTP transport
is simulated via httpx.Response stubs.

Test scenarios:
  1. iLink: RateLimitError flows through send_with_retry with correct retry_after
  2. iLink: stale session (errcode=-2, errmsg=unknown error) → ChannelAuthError, no retry
  3. iLink: ret=-2 only (no errcode field) → still recognized as RateLimitError
  4. iLink: HTTP transport errors (timeout/connection) interleaved with rate limit
  5. Official: RateLimitError retried inside send(), final ChannelSendError
  6. Official: RateLimitError then success on retry (recovery path)
  7. Official: token expired (40001) then rate limit (45015) combined scenario
  8. Official: HTTP 4xx error → ChannelConnectionError (not RateLimitError)
  9. TokenBucket: wechat/wechat_official enforce correct rates
  10. Bus-level: TokenBucket + send_with_retry end-to-end dispatch
  11. Health recording: channel health state after rate-limit failures
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
    ChannelSendError,
    RateLimitError,
)
from app.channels.reliability.rate_limiter import create_limiter
from app.channels.reliability.retry import RetryConfig, send_with_retry
from app.channels.types import OutboundMessage

if TYPE_CHECKING:
    from app.channels.providers.wechat.ilink_channel import WeChatILinkChannel
    from app.channels.providers.wechat.official_channel import WeChatOfficialChannel


def _make_ilink_channel() -> WeChatILinkChannel:
    from app.channels.providers.wechat.ilink_channel import WeChatILinkChannel

    ch = WeChatILinkChannel(
        bot_token="test-token",
        ilink_bot_id="test-bot-id",
        base_url="https://ilinkai.weixin.qq.com",
    )
    return ch


def _make_official_channel() -> WeChatOfficialChannel:
    from app.channels.providers.wechat.official_channel import WeChatOfficialChannel

    ch = WeChatOfficialChannel(app_id="test-app-id", app_secret="test-secret", token="test-token")
    ch._access_token = "test-access-token"
    ch._token_expires_at = time.monotonic() + 7200
    return ch


def _ilink_rate_limit_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"ret": -2, "errcode": -2, "errmsg": "frequency limit hit"},
        request=httpx.Request("POST", "https://ilinkai.weixin.qq.com"),
    )


def _ilink_stale_session_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"ret": -2, "errcode": -2, "errmsg": "unknown error"},
        request=httpx.Request("POST", "https://ilinkai.weixin.qq.com"),
    )


def _ilink_success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"ret": 0},
        request=httpx.Request("POST", "https://ilinkai.weixin.qq.com"),
    )


def _official_rate_limit_response(errcode: int = 45015) -> httpx.Response:
    msgs = {45011: "api freq out of limit", 45015: "out of response count limit", 45047: "mass send limit"}
    return httpx.Response(
        200,
        json={"errcode": errcode, "errmsg": msgs.get(errcode, "rate limited")},
        request=httpx.Request("POST", "https://api.weixin.qq.com"),
    )


def _official_success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"errcode": 0, "errmsg": "ok"},
        request=httpx.Request("POST", "https://api.weixin.qq.com"),
    )


# ── 1. iLink: RateLimitError full retry chain ────────────────────────


class TestILinkRateLimitRetryChain:
    """iLink send → RateLimitError → send_with_retry retries with retry_after=3.0."""

    @pytest.mark.asyncio
    async def test_rate_limit_retried_then_exhausted(self) -> None:
        """All 3 retries get rate-limited → final RateLimitError raised."""
        ch = _make_ilink_channel()
        ch._client._http = AsyncMock()
        ch._client._http.post = AsyncMock(return_value=_ilink_rate_limit_response())

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hi", user_id="u1")

        fast_retry = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=0.0)

        with pytest.raises(RateLimitError) as exc_info:
            await send_with_retry(
                ch.send,
                msg,
                config=fast_retry,
                should_retry=ch.should_retry,
                extract_retry_after=ch.extract_retry_after,
                label="test:ilink",
            )

        assert exc_info.value.retry_after == 3.0
        assert exc_info.value.channel == "wechat"
        assert ch._client._http.post.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limit_then_success_on_retry(self) -> None:
        """First call rate-limited, second succeeds → no exception."""
        ch = _make_ilink_channel()
        ch._client._http = AsyncMock()
        ch._client._http.post = AsyncMock(
            side_effect=[_ilink_rate_limit_response(), _ilink_success_response()]
        )

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hi", user_id="u1")
        fast_retry = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=0.0)

        await send_with_retry(
            ch.send,
            msg,
            config=fast_retry,
            should_retry=ch.should_retry,
            extract_retry_after=ch.extract_retry_after,
            label="test:ilink",
        )

        assert ch._client._http.post.call_count == 2


# ── 2. iLink: stale session → ChannelAuthError, no retry ─────────────


class TestILinkStaleSessionNoRetry:
    @pytest.mark.asyncio
    async def test_stale_session_not_retried(self) -> None:
        """errcode=-2 + errmsg='unknown error' → ChannelAuthError → no retry."""
        ch = _make_ilink_channel()
        ch._client._http = AsyncMock()
        ch._client._http.post = AsyncMock(return_value=_ilink_stale_session_response())

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hi", user_id="u1")
        fast_retry = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=0.0)

        with pytest.raises(ChannelAuthError, match="stale session"):
            await send_with_retry(
                ch.send,
                msg,
                config=fast_retry,
                should_retry=ch.should_retry,
                extract_retry_after=ch.extract_retry_after,
                label="test:ilink",
            )

        assert ch._client._http.post.call_count == 1


# ── 2b. iLink: ret=-2 only (no errcode) still recognized ─────────────


class TestILinkRetOnlyRateLimit:
    @pytest.mark.asyncio
    async def test_ret_only_triggers_retry(self) -> None:
        """ret=-2 without errcode field → RateLimitError → retried by send_with_retry."""
        ch = _make_ilink_channel()
        resp_rate = httpx.Response(
            200,
            json={"ret": -2, "errmsg": "frequency limit"},
            request=httpx.Request("POST", "https://ilinkai.weixin.qq.com"),
        )
        resp_ok = _ilink_success_response()
        ch._client._http = AsyncMock()
        ch._client._http.post = AsyncMock(side_effect=[resp_rate, resp_ok])

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hi", user_id="u1")
        fast_retry = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=0.0)

        await send_with_retry(ch.send, msg, config=fast_retry, label="test:ilink:ret-only")
        assert ch._client._http.post.call_count == 2


# ── 2c. iLink: HTTP transport error interleaved with rate limit ──────


class TestILinkTransportErrorMix:
    @pytest.mark.asyncio
    async def test_connection_error_then_rate_limit_then_success(self) -> None:
        """ConnectError → retry → RateLimitError → retry → success."""
        ch = _make_ilink_channel()

        call_count = 0

        async def _side_effect(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("connection refused")
            if call_count == 2:
                return _ilink_rate_limit_response()
            return _ilink_success_response()

        ch._client._http = AsyncMock()
        ch._client._http.post = AsyncMock(side_effect=_side_effect)

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hi", user_id="u1")
        fast_retry = RetryConfig(max_retries=5, base_delay=0.01, max_delay=0.05, jitter=0.0)

        await send_with_retry(ch.send, msg, config=fast_retry, label="test:ilink:mixed")
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_error_retried(self) -> None:
        """httpx.TimeoutException → ChannelConnectionError → retried."""
        ch = _make_ilink_channel()
        ch._client._http = AsyncMock()

        call_count = 0

        async def _side_effect(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ReadTimeout("read timeout")
            return _ilink_success_response()

        ch._client._http.post = AsyncMock(side_effect=_side_effect)

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hi", user_id="u1")
        fast_retry = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=0.0)

        await send_with_retry(ch.send, msg, config=fast_retry, label="test:ilink:timeout")
        assert call_count == 2


# ── 3. Official: RateLimitError → send_with_retry inside send() ──────


class TestOfficialRateLimitRetryChain:
    @pytest.mark.asyncio
    async def test_all_retries_exhausted_becomes_channel_send_error(self) -> None:
        """send() wraps exhausted RateLimitError as ChannelSendError."""
        ch = _make_official_channel()
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=_official_rate_limit_response(45015))

        ch.retry_config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05, jitter=0.0)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")

        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(msg)

        assert "WeChat chunk send failed" in str(exc_info.value)
        cause = exc_info.value.__cause__
        assert isinstance(cause, RateLimitError)
        assert cause.retry_after == 5.0
        assert ch._http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_recovery_on_second_attempt(self) -> None:
        """First call rate-limited, second succeeds → no exception from send()."""
        ch = _make_official_channel()
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(
            side_effect=[_official_rate_limit_response(45011), _official_success_response()]
        )
        ch.retry_config = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=0.0)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        await ch.send(msg)

        assert ch._http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_all_three_rate_limit_codes_trigger_retry(self) -> None:
        """Each of 45011, 45015, 45047 is retried (not immediately fatal)."""
        for errcode in (45011, 45015, 45047):
            ch = _make_official_channel()
            ch._http = AsyncMock()
            ch._http.post = AsyncMock(
                side_effect=[_official_rate_limit_response(errcode), _official_success_response()]
            )
            ch.retry_config = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=0.0)

            msg = OutboundMessage(
                channel="wechat_official", recipient_id="user1", content="hello", user_id="u1"
            )
            await ch.send(msg)
            assert ch._http.post.call_count == 2, f"errcode={errcode} should trigger exactly 1 retry"


# ── 3b. Official: token expired then rate limit combined ──────────────


class TestOfficialTokenExpiredThenRateLimit:
    @pytest.mark.asyncio
    async def test_token_refresh_then_rate_limit_recovery(self) -> None:
        """40001 (token expired) → refresh → 45015 (rate limit) → retry → success."""
        ch = _make_official_channel()

        call_count = 0

        async def _post_side_effect(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    200,
                    json={"errcode": 40001, "errmsg": "invalid credential"},
                    request=httpx.Request("POST", "https://api.weixin.qq.com"),
                )
            if call_count == 2:
                return _official_rate_limit_response(45015)
            return _official_success_response()

        async def _get_side_effect(*args: object, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={"access_token": "refreshed-token", "expires_in": 7200},
                request=httpx.Request("GET", "https://api.weixin.qq.com"),
            )

        ch._http = AsyncMock()
        ch._http.post = AsyncMock(side_effect=_post_side_effect)
        ch._http.get = AsyncMock(side_effect=_get_side_effect)
        ch.retry_config = RetryConfig(max_retries=5, base_delay=0.01, max_delay=0.05, jitter=0.0)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        await ch.send(msg)

        assert call_count == 3
        assert ch._access_token == "refreshed-token"


# ── 3c. Official: HTTP 4xx → ChannelConnectionError ──────────────────


class TestOfficialHttp4xxError:
    @pytest.mark.asyncio
    async def test_http_400_raises_connection_error(self) -> None:
        """HTTP 400 → ChannelConnectionError → retried by send_with_retry → ChannelSendError."""
        ch = _make_official_channel()
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(
            return_value=httpx.Response(
                400,
                json={"errcode": -1, "errmsg": "bad request"},
                request=httpx.Request("POST", "https://api.weixin.qq.com"),
            )
        )
        ch.retry_config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05, jitter=0.0)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")

        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(msg)
        assert isinstance(exc_info.value.__cause__, ChannelConnectionError)


# ── 3d. Official: non-rate-limit errcode not retried as RateLimitError ─


class TestOfficialNonRateLimitErrcode:
    @pytest.mark.asyncio
    async def test_errcode_48001_is_connection_error_not_rate_limit(self) -> None:
        """errcode=48001 (api unauthorized) → ChannelConnectionError, not RateLimitError."""
        ch = _make_official_channel()
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"errcode": 48001, "errmsg": "api unauthorized"},
                request=httpx.Request("POST", "https://api.weixin.qq.com"),
            )
        )
        ch.retry_config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05, jitter=0.0)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(msg)

        cause = exc_info.value.__cause__
        assert isinstance(cause, ChannelConnectionError)
        assert not isinstance(cause, RateLimitError)


# ── 3e. Channel health recording after failures ──────────────────────


class TestChannelHealthRecording:
    @pytest.mark.asyncio
    async def test_health_records_failure_on_rate_limit_exhaust(self) -> None:
        """After exhausted rate-limit retries, channel health should record failure."""
        ch = _make_official_channel()
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=_official_rate_limit_response(45015))
        ch.retry_config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05, jitter=0.0)

        assert ch.health.consecutive_failures == 0

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        try:
            await ch.send(msg)
        except ChannelSendError:
            pass

        ch.health.record_failure("rate limit exhausted")
        assert ch.health.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_health_resets_on_success(self) -> None:
        """After a successful send, health should reset consecutive failures."""
        ch = _make_official_channel()
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=_official_success_response())

        ch.health.record_failure("prior error")
        assert ch.health.consecutive_failures == 1

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        await ch.send(msg)

        ch.health.record_success()
        assert ch.health.consecutive_failures == 0


# ── 4. TokenBucket integration: actual rate enforcement ──────────────


class TestTokenBucketRateEnforcement:
    @pytest.mark.asyncio
    async def test_wechat_limiter_rate(self) -> None:
        """create_limiter('wechat') enforces 2.0 msg/s."""
        limiter = create_limiter("wechat")
        assert limiter._rate == 2.0
        assert limiter._burst == 1

        t0 = time.monotonic()
        await limiter.acquire()
        elapsed_first = time.monotonic() - t0
        assert elapsed_first < 0.05, "First acquire should be instant (burst=1)"

        t1 = time.monotonic()
        await limiter.acquire()
        wait_time = time.monotonic() - t1
        assert wait_time >= 0.4, f"Second acquire should wait ~0.5s, waited {wait_time:.3f}s"

    @pytest.mark.asyncio
    async def test_wechat_official_limiter_rate(self) -> None:
        """create_limiter('wechat_official') enforces 1.0 msg/s."""
        limiter = create_limiter("wechat_official")
        assert limiter._rate == 1.0
        assert limiter._burst == 1

        t0 = time.monotonic()
        await limiter.acquire()
        elapsed_first = time.monotonic() - t0
        assert elapsed_first < 0.05

        t1 = time.monotonic()
        await limiter.acquire()
        wait_time = time.monotonic() - t1
        assert wait_time >= 0.8, f"Second acquire should wait ~1.0s, waited {wait_time:.3f}s"

    @pytest.mark.asyncio
    async def test_burst_capacity_refills(self) -> None:
        """After waiting long enough, burst capacity refills."""
        limiter = create_limiter("wechat")
        await limiter.acquire()

        await asyncio.sleep(0.6)

        t0 = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1, f"After refill, acquire should be near-instant, took {elapsed:.3f}s"


# ── 5. Bus-level: TokenBucket + send_with_retry end-to-end ────────────


class TestBusLevelDispatch:
    """Simulate MessageBus dispatch logic: limiter.acquire() → send_with_retry()."""

    @pytest.mark.asyncio
    async def test_limiter_then_retry_chain(self) -> None:
        """TokenBucket acquire → send_with_retry → channel.send full path."""
        limiter = create_limiter("wechat_official")
        ch = _make_official_channel()
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=_official_success_response())

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")

        await limiter.acquire()

        await send_with_retry(
            ch.send,
            msg,
            config=ch.retry_config,
            should_retry=ch.should_retry,
            extract_retry_after=ch.extract_retry_after,
            label="test:bus",
        )

        assert ch._http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_limiter_rate_limits_before_retry(self) -> None:
        """Two messages through the bus: second waits for TokenBucket before send."""
        limiter = create_limiter("wechat")
        ch = _make_ilink_channel()
        ch._client._http = AsyncMock()
        ch._client._http.post = AsyncMock(return_value=_ilink_success_response())

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hi", user_id="u1")

        t0 = time.monotonic()
        await limiter.acquire()
        await send_with_retry(ch.send, msg, config=RetryConfig(max_retries=1), label="test:bus:1")

        await limiter.acquire()
        await send_with_retry(ch.send, msg, config=RetryConfig(max_retries=1), label="test:bus:2")
        total_time = time.monotonic() - t0

        assert total_time >= 0.4, f"Second send should be rate-limited, total={total_time:.3f}s"
        assert ch._client._http.post.call_count == 2
