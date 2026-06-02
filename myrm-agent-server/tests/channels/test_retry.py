"""Tests for channels/retry: per-channel retry with jitter and max delay."""

import pytest

from app.channels.reliability.retry import (
    RetryConfig,
    _apply_jitter,
    default_extract_retry_after,
    default_should_retry,
    send_with_retry,
)


class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 30.0
        assert cfg.jitter == 0.1

    def test_frozen(self):
        cfg = RetryConfig()
        with pytest.raises(AttributeError):
            cfg.max_retries = 5  # type: ignore[misc]


class TestDefaultShouldRetry:
    def test_os_error(self):
        assert default_should_retry(OSError("conn refused"))

    def test_timeout_error(self):
        assert default_should_retry(TimeoutError())

    def test_connection_error(self):
        assert default_should_retry(ConnectionError())

    def test_value_error_not_retryable(self):
        assert not default_should_retry(ValueError("bad input"))


class TestDefaultExtractRetryAfter:
    def test_no_response(self):
        assert default_extract_retry_after(OSError()) is None

    def test_non_429(self):
        exc = _exc_with_response(status=500, headers={})
        assert default_extract_retry_after(exc) is None

    def test_429_with_retry_after(self):
        exc = _exc_with_response(status=429, headers={"retry-after": "5"})
        assert default_extract_retry_after(exc) == 5.0

    def test_429_without_header(self):
        exc = _exc_with_response(status=429, headers={})
        assert default_extract_retry_after(exc) is None


class TestApplyJitter:
    def test_zero_jitter(self):
        assert _apply_jitter(1.0, 0.0) == 1.0

    def test_positive_jitter_bounded(self):
        for _ in range(100):
            result = _apply_jitter(10.0, 0.1)
            assert 9.0 <= result <= 11.0

    def test_never_negative(self):
        for _ in range(100):
            assert _apply_jitter(0.01, 1.0) >= 0.0


class TestSendWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        calls = []

        async def fn(x: int) -> int:
            calls.append(x)
            return x * 2

        result = await send_with_retry(fn, 5)
        assert result == 10
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        attempt = 0

        async def fn() -> str:
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise OSError("connection reset")
            return "ok"

        config = RetryConfig(max_retries=3, base_delay=0.01, jitter=0.0)
        result = await send_with_retry(fn, config=config)
        assert result == "ok"
        assert attempt == 3

    @pytest.mark.asyncio
    async def test_raises_non_retryable(self):
        async def fn() -> None:
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent"):
            await send_with_retry(fn)

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        async def fn() -> None:
            raise OSError("always fails")

        config = RetryConfig(max_retries=2, base_delay=0.01, jitter=0.0)
        with pytest.raises(OSError, match="always fails"):
            await send_with_retry(fn, config=config)

    @pytest.mark.asyncio
    async def test_custom_should_retry(self):
        attempt = 0

        async def fn() -> str:
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise ValueError("retryable in custom logic")
            return "recovered"

        config = RetryConfig(max_retries=3, base_delay=0.01, jitter=0.0)
        result = await send_with_retry(
            fn,
            config=config,
            should_retry=lambda exc: isinstance(exc, ValueError),
        )
        assert result == "recovered"
        assert attempt == 2

    @pytest.mark.asyncio
    async def test_respects_max_delay(self):
        attempt = 0

        async def fn() -> str:
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise OSError("fail")
            return "ok"

        config = RetryConfig(max_retries=3, base_delay=100.0, max_delay=0.01, jitter=0.0)
        result = await send_with_retry(fn, config=config)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_uses_extract_retry_after(self):
        attempt = 0

        async def fn() -> str:
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise OSError("rate limited")
            return "ok"

        config = RetryConfig(max_retries=2, base_delay=100.0, max_delay=200.0, jitter=0.0)
        result = await send_with_retry(
            fn,
            config=config,
            extract_retry_after=lambda _: 0.01,
        )
        assert result == "ok"


# --- helpers ---


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str]) -> None:
        self.status_code = status_code
        self.headers = headers


def _exc_with_response(status: int, headers: dict[str, str]) -> OSError:
    exc = OSError("http error")
    exc.response = _FakeResponse(status, headers)  # type: ignore[attr-defined]
    return exc
