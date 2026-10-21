"""Retry policy for media downloads.

[INPUT]
- (none)

[OUTPUT]
- RetryPolicy: Retry policy for failed tasks.
- retry_with_policy: Execute function with retry policy.

[POS]
Retry policy for media downloads.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    """Retry policy with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts. Default: 3.
        base_delay: Initial delay in seconds before first retry. Default: 1.0.
        max_delay: Maximum delay in seconds between retries. Default: 10.0.
        exponential_base: Base for exponential backoff. Default: 2.0.
        retryable_exceptions: Tuple of exception types that trigger retry.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given retry attempt (0-indexed).

        Uses exponential backoff: delay = base_delay * (exponential_base ** attempt)
        Capped at max_delay.
        """
        delay = self.base_delay * (self.exponential_base**attempt)
        return min(delay, self.max_delay)

    def should_retry(self, exception: Exception) -> bool:
        """Check if exception is retryable."""
        return isinstance(exception, self.retryable_exceptions)


T = TypeVar("T")


async def retry_with_policy(
    func: callable[..., T],
    *args: object,
    policy: RetryPolicy,
    **kwargs: object,
) -> T:
    """Execute function with retry policy.

    Args:
        func: Async function to execute.
        *args: Positional arguments for func.
        policy: Retry policy to use.
        **kwargs: Keyword arguments for func.

    Returns:
        Result of func.

    Raises:
        Last exception if all retries exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exception = exc

            if attempt >= policy.max_retries:
                logger.debug(
                    "Retry exhausted after %d attempts: %s",
                    attempt + 1,
                    exc,
                )
                raise

            if not policy.should_retry(exc):
                logger.debug(
                    "Exception not retryable: %s",
                    type(exc).__name__,
                )
                raise

            delay = policy.calculate_delay(attempt)
            logger.debug(
                "Retry attempt %d/%d after %.2fs: %s",
                attempt + 1,
                policy.max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    raise last_exception or RuntimeError("Unexpected: no exception raised")
