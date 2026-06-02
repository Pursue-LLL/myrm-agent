"""Per-channel retry with exponential backoff, jitter, and max delay.

Channel providers declare retry_config + should_retry + extract_retry_after;
send_with_retry receives these parameters as a pure function to execute retry logic.

[INPUT]
(no external dependencies, pure asyncio implementation)
- infra.tracing (POS: distributed tracing)

[OUTPUT]
- RetryConfig: retry configuration dataclass
- send_with_retry(): async retry wrapper with exponential backoff and jitter

[POS]
Async retry utility with exponential backoff. Channel providers declare retry policies;
send_with_retry executes generic retry logic as a pure function.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from myrm_agent_harness.infra.tracing import get_tracer

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
    ChannelSendError,
    RateLimitError,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

_T = TypeVar("_T")

DEFAULT_RETRYABLE = (
    OSError,  # covers ConnectionError, httpx.ConnectError, etc.
    TimeoutError,  # covers asyncio.TimeoutError (alias since 3.11)
)


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Per-channel retry parameters.

    Channel providers declare a class-level retry_config to customize
    retry behavior. send_with_retry uses these values.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.1


_DEFAULT_CONFIG = RetryConfig()


def default_should_retry(exc: BaseException) -> bool:
    """Retryability check supporting both ChannelError hierarchy and raw exceptions.

    Decision matrix:
        ChannelAuthError        → never retry
        RateLimitError          → always retry
        ChannelSendError        → retry if ``retriable`` flag is True
        ChannelConnectionError  → always retry
        OSError / TimeoutError  → always retry (transport-level)
    """
    if isinstance(exc, ChannelAuthError):
        return False
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, ChannelSendError):
        return exc.retriable
    if isinstance(exc, ChannelConnectionError):
        return True
    return isinstance(exc, DEFAULT_RETRYABLE)


def default_extract_retry_after(exc: BaseException) -> float | None:
    """Extract retry-after seconds from RateLimitError or HTTP 429 responses."""
    if isinstance(exc, RateLimitError):
        return exc.retry_after

    response = getattr(exc, "response", None)
    if response is None:
        return None
    status = getattr(response, "status_code", 0)
    if status != 429:
        return None
    headers = getattr(response, "headers", {})
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _apply_jitter(delay: float, jitter: float) -> float:
    if jitter <= 0:
        return delay
    offset = (random.random() * 2 - 1) * jitter
    return max(0.0, delay * (1 + offset))


async def send_with_retry(
    fn: Callable[..., Awaitable[_T]],
    *args: object,
    config: RetryConfig = _DEFAULT_CONFIG,
    should_retry: Callable[[BaseException], bool] = default_should_retry,
    extract_retry_after: Callable[[BaseException], float | None] = default_extract_retry_after,
    label: str = "send",
) -> _T:
    """Execute *fn* with configurable retry, exponential backoff, and jitter.

    Args:
        fn: Async callable to execute.
        *args: Positional arguments forwarded to *fn*.
        config: Retry parameters (max_retries, base_delay, max_delay, jitter).
        should_retry: Predicate to decide if an exception is retryable.
        extract_retry_after: Extract platform-specific retry-after seconds.
        label: Human-readable label for log messages.
    """
    last_error: BaseException | None = None

    with tracer.start_as_current_span(f"retry:{label}") as span:
        span.set_attribute("retry.max_retries", config.max_retries)
        span.set_attribute("retry.base_delay", config.base_delay)

        attempt = 0
        while attempt < config.max_retries:
            try:
                result = await fn(*args)
                span.set_attribute("retry.attempts", attempt + 1)
                span.set_attribute("retry.success", True)
                return result

            except BaseException as exc:
                is_retryable = should_retry(exc)

                # If the error is non-retryable OR we've exhausted retries, try stripping media as a fallback
                if not is_retryable or attempt >= config.max_retries - 1:
                    msg = args[0] if args else None
                    if msg and hasattr(msg, "strip_media") and getattr(msg, "media", None):
                        new_msg = msg.strip_media()
                        if new_msg is not msg:
                            args = (new_msg,) + args[1:]
                            logger.warning(
                                "Channel %s encountered error with media: %s. Stripped media and retrying text.",
                                label,
                                exc,
                            )
                            attempt = 0  # Reset attempt counter for the stripped message
                            continue

                if not is_retryable:
                    span.set_attribute("retry.non_retryable", True)
                    span.set_attribute("error.type", type(exc).__name__)
                    span.record_exception(exc)
                    raise

                last_error = exc

                if attempt >= config.max_retries - 1:
                    break

                retry_after = extract_retry_after(exc)
                if retry_after is not None:
                    delay = min(retry_after, config.max_delay)
                else:
                    delay = min(config.base_delay * (2**attempt), config.max_delay)
                delay = _apply_jitter(delay, config.jitter)

                # Record retry event
                span.add_event(
                    "retry_attempt",
                    attributes={
                        "attempt": attempt + 1,
                        "delay_s": delay,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )

                logger.warning(
                    "Channel %s failed (attempt %d/%d), retrying in %.1fs: %s",
                    label,
                    attempt + 1,
                    config.max_retries,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                attempt += 1

        # All retries exhausted
        span.set_attribute("retry.attempts", config.max_retries)
        span.set_attribute("retry.success", False)
        span.set_attribute("error.type", type(last_error).__name__ if last_error else "Unknown")
        if last_error:
            span.record_exception(last_error)

        raise last_error  # type: ignore[misc]
