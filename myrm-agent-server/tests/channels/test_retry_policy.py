"""Unit and benchmark tests for RetryPolicy."""

from __future__ import annotations

import asyncio

import pytest

from app.channels.routing.retry_policy import RetryConfig, RetryPolicy


class TestRetryPolicy:
    """Unit tests for RetryPolicy component."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        """Should succeed immediately on first attempt."""
        policy = RetryPolicy(RetryConfig(max_retries=3))

        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = await policy.execute(
            operation=operation,
            session_key="test_session",
        )

        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 1
        assert result.total_delay == 0.0
        assert result.final_error is None
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_success_on_retry(self) -> None:
        """Should succeed after retries."""
        policy = RetryPolicy(RetryConfig(max_retries=3, base_delay=0.01))

        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Temporary failure")
            return "success"

        result = await policy.execute(
            operation=operation,
            session_key="test_session",
        )

        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 3
        assert result.total_delay > 0.0
        assert result.final_error is None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_failure_all_retries_exhausted(self) -> None:
        """Should fail after all retries exhausted."""
        policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.01))

        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Persistent failure")

        result = await policy.execute(
            operation=operation,
            session_key="test_session",
        )

        assert result.success is False
        assert result.result is None
        assert result.attempts == 3
        assert result.total_delay > 0.0
        assert isinstance(result.final_error, RuntimeError)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff(self) -> None:
        """Should use exponential backoff delays."""
        policy = RetryPolicy(RetryConfig(max_retries=3, base_delay=0.01, backoff_multiplier=2.0))

        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First failure")
            return "success"

        start = asyncio.get_event_loop().time()
        result = await policy.execute(
            operation=operation,
            session_key="test_session",
        )
        elapsed = asyncio.get_event_loop().time() - start

        assert result.success is True
        assert result.attempts == 2
        assert elapsed >= 0.01

    @pytest.mark.asyncio
    async def test_on_retry_callback(self) -> None:
        """Should call on_retry_callback on retry attempts."""
        policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.01))

        call_count = 0
        retry_callbacks: list[tuple[int, float]] = []

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Failure")
            return "success"

        async def on_retry(attempt: int, delay: float) -> None:
            retry_callbacks.append((attempt, delay))

        result = await policy.execute(
            operation=operation,
            session_key="test_session",
            on_retry_callback=on_retry,
        )

        assert result.success is True
        assert len(retry_callbacks) == 2
        assert retry_callbacks[0][0] == 1
        assert retry_callbacks[1][0] == 2

    @pytest.mark.asyncio
    async def test_callback_exception_handling(self) -> None:
        """Should handle exceptions in on_retry_callback gracefully."""
        policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.01))

        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Failure")
            return "success"

        async def failing_callback(attempt: int, delay: float) -> None:
            raise ValueError("Callback error")

        result = await policy.execute(
            operation=operation,
            session_key="test_session",
            on_retry_callback=failing_callback,
        )

        assert result.success is True
        assert result.attempts == 2


class TestRetryPolicyBenchmark:
    """Benchmark tests for RetryPolicy performance."""

    @pytest.mark.benchmark(group="retry_policy")
    def test_benchmark_success_path(self, benchmark) -> None:
        """Benchmark success on first attempt path."""
        policy = RetryPolicy(RetryConfig())

        async def operation() -> str:
            return "success"

        async def run():
            return await policy.execute(
                operation=operation,
                session_key="bench_session",
            )

        result = benchmark(lambda: asyncio.run(run()))
        assert result.success is True

    @pytest.mark.benchmark(group="retry_policy")
    def test_benchmark_retry_path(self, benchmark) -> None:
        """Benchmark retry path with one retry."""

        async def run():
            policy = RetryPolicy(RetryConfig(max_retries=2, base_delay=0.001))
            call_count = 0

            async def operation() -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise RuntimeError("First failure")
                return "success"

            return await policy.execute(
                operation=operation,
                session_key="bench_session",
            )

        result = benchmark(lambda: asyncio.run(run()))
        assert result.success is True
        assert result.attempts == 2
