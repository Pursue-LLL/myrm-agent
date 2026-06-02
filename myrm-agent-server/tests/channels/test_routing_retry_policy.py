"""RetryPolicy tests — exponential backoff, callbacks, edge cases."""

from __future__ import annotations

import pytest

from app.channels.routing.retry_policy import (
    RetryConfig,
    RetryPolicy,
    RetryResult,
)


class TestRetryConfig:
    def test_defaults(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.base_delay == 0.5
        assert cfg.backoff_multiplier == 2.0
        assert cfg.ui_feedback is True

    def test_custom(self) -> None:
        cfg = RetryConfig(max_retries=5, base_delay=1.0, backoff_multiplier=3.0, ui_feedback=False)
        assert cfg.max_retries == 5
        assert cfg.base_delay == 1.0


class TestRetryResult:
    def test_success_result(self) -> None:
        r = RetryResult(success=True, result=42, attempts=1, total_delay=0.0, final_error=None)
        assert r.success is True
        assert r.result == 42
        assert r.attempts == 1
        assert r.final_error is None

    def test_failure_result(self) -> None:
        err = RuntimeError("fail")
        r = RetryResult(success=False, result=None, attempts=3, total_delay=1.5, final_error=err)
        assert r.success is False
        assert r.result is None
        assert r.final_error is err


class TestRetryPolicyExecute:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        policy = RetryPolicy(RetryConfig(max_retries=3, base_delay=0.001))

        async def op() -> str:
            return "ok"

        result = await policy.execute(op, "sess-1")
        assert result.success is True
        assert result.result == "ok"
        assert result.attempts == 1
        assert result.total_delay == 0.0

    @pytest.mark.asyncio
    async def test_success_on_retry(self) -> None:
        call_count = 0
        policy = RetryPolicy(RetryConfig(max_retries=3, base_delay=0.001))

        async def op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("fail")
            return "recovered"

        result = await policy.execute(op, "sess-2")
        assert result.success is True
        assert result.result == "recovered"
        assert result.attempts == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self) -> None:
        policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.001))

        async def op() -> str:
            raise ValueError("always fails")

        result = await policy.execute(op, "sess-3")
        assert result.success is False
        assert result.result is None
        assert result.attempts == 3
        assert isinstance(result.final_error, ValueError)

    @pytest.mark.asyncio
    async def test_zero_retries(self) -> None:
        policy = RetryPolicy(RetryConfig(max_retries=0, base_delay=0.001))

        async def op() -> str:
            raise RuntimeError("no retry")

        result = await policy.execute(op, "sess-4")
        assert result.success is False
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_callback_invoked_on_retry(self) -> None:
        call_count = 0
        callback_calls: list[tuple[int, float]] = []
        policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.001, ui_feedback=True))

        async def op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first fail")
            return "ok"

        async def on_retry(attempt: int, delay: float) -> None:
            callback_calls.append((attempt, delay))

        result = await policy.execute(op, "sess-5", on_retry_callback=on_retry)
        assert result.success is True
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == 1

    @pytest.mark.asyncio
    async def test_callback_not_invoked_when_ui_feedback_off(self) -> None:
        call_count = 0
        callback_calls: list[tuple[int, float]] = []
        policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.001, ui_feedback=False))

        async def op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("fail")
            return "ok"

        async def on_retry(attempt: int, delay: float) -> None:
            callback_calls.append((attempt, delay))

        result = await policy.execute(op, "sess-6", on_retry_callback=on_retry)
        assert result.success is True
        assert len(callback_calls) == 0

    @pytest.mark.asyncio
    async def test_callback_error_silenced(self) -> None:
        call_count = 0
        policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.001))

        async def op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("fail")
            return "ok"

        async def bad_callback(attempt: int, delay: float) -> None:
            raise TypeError("callback broken")

        result = await policy.execute(op, "sess-7", on_retry_callback=bad_callback)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_total_delay_accumulates(self) -> None:
        call_count = 0
        policy = RetryPolicy(RetryConfig(max_retries=3, base_delay=0.001, backoff_multiplier=2.0))

        async def op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("fail")
            return "ok"

        result = await policy.execute(op, "sess-8")
        assert result.success is True
        assert result.total_delay > 0
