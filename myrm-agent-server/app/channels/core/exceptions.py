"""Channel exception hierarchy for precise retry and error handling.

Enables Gateway retry logic to distinguish retriable vs non-retriable errors
and extract platform-specific retry-after hints.

Hierarchy:
    ChannelError
    ├── ChannelSendError      — message delivery failed (``accepted`` = partially delivered)
    │   ├── DeliveryUnconfirmedError — send() returned no id although the channel reports ids
    │   └── RateLimitError    — platform rate limit hit (carries retry_after)
    ├── ChannelAuthError      — credentials invalid or expired (never retry)
    └── ChannelConnectionError — transport layer failure (always retry)

[INPUT]
- (none)

[OUTPUT]
- ChannelError: Base exception for all channel-related errors.
- ChannelSendError: Message delivery failed; ``accepted`` marks a partial delivery, ``retriable`` also reads the wrapped ``httpx`` error, ``for_attachments`` / ``from_http_status`` build typed failures.
- may_have_reached_platform: whether an ``httpx`` failure may come after the platform took the request.
- DeliveryUnconfirmedError: send() returned no message id on a channel that reports ids.
- RateLimitError: Platform rate limit hit. Always retriable with specific d...
- ChannelAuthError: Credentials invalid or expired. Never retry — requires re...
- ChannelConnectionError: Transport layer failure (DNS, timeout, connection reset)....

[POS]
Channel exception hierarchy for precise retry and error handling.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

# A request that failed before it left this process: nothing reached the platform, so sending it again cannot
# show the reply twice. Any other ``httpx.RequestError`` (a timeout while waiting for the answer, a reset, a
# malformed reply) may come after the platform took the message.
_REQUEST_NEVER_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.ProxyError)


def may_have_reached_platform(exc: BaseException | None) -> bool:
    """Whether ``exc`` is an ``httpx`` failure that may come after the platform took the request.

    The outcome of such a request is unknown, so sending the message again could show it twice. Any other
    exception, and no exception at all, is no evidence of that.
    """
    return isinstance(exc, httpx.RequestError) and not isinstance(exc, _REQUEST_NEVER_SENT)


class ChannelError(Exception):
    """Base exception for all channel-related errors."""

    def __init__(self, message: str, *, channel: str = "") -> None:
        super().__init__(message)
        self.channel = channel


class ChannelSendError(ChannelError):
    """Message delivery failed. May be retriable depending on status code.

    ``accepted`` marks a partial delivery: the platform already accepted part of the
    message (text chunks or other attachments) before the failure, so the sender must
    neither retry nor degrade the message — that would duplicate what the recipient
    already received. ``failed_attachments`` names the attachments that did not arrive; a partial
    delivery without names means only text chunks are missing.

    ``retriable`` is the flag the error was built with, unless the error was raised ``from`` an ``httpx``
    failure that may come after the platform took the request: such an error is never retriable, so a
    provider that wraps transport errors cannot forget to classify them.
    """

    def __init__(
        self,
        message: str,
        *,
        channel: str = "",
        status_code: int = 0,
        retriable: bool = True,
        accepted: bool = False,
        failed_attachments: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message, channel=channel)
        self.status_code = status_code
        self._retriable = retriable
        self.accepted = accepted
        self.failed_attachments = failed_attachments

    @property
    def retriable(self) -> bool:
        """Whether sending the message again may succeed without showing it twice."""
        return self._retriable and not may_have_reached_platform(self.__cause__)

    @classmethod
    def for_attachments(
        cls, channel: str, failed: Sequence[str], *, delivered_any: bool, retriable: bool = True
    ) -> ChannelSendError:
        """Error for attachments the platform did not take, built after every attachment was attempted.

        ``delivered_any`` says whether text or other attachments already reached the recipient. Then the
        failure is a partial delivery (never retried, only the named attachments are re-recorded);
        otherwise nothing arrived yet and the sender may retry, falling back to text only.
        """
        names = tuple(failed)
        return cls(
            f"Failed to deliver attachment(s): {', '.join(names)}",
            channel=channel,
            retriable=retriable and not delivered_any,
            accepted=delivered_any,
            failed_attachments=names,
        )

    @classmethod
    def for_text_chunks(cls, channel: str, *, delivered: int, total: int, cause: BaseException) -> ChannelSendError:
        """Error for a reply whose text stopped after ``delivered`` of ``total`` chunks.

        The recipient already holds the first chunks, so the failure is a partial delivery: never retried,
        because a replay would send those chunks a second time.
        """
        return cls(
            f"Delivered {delivered} of {total} text chunks, the next one failed: {cause}",
            channel=channel,
            status_code=cause.status_code if isinstance(cause, ChannelSendError) else 0,
            retriable=False,
            accepted=True,
        )

    @classmethod
    def from_http_status(cls, channel: str, status_code: int, detail: str = "") -> ChannelSendError:
        """Error for an HTTP rejection: timeouts, throttling and server faults may succeed on a re-send, other 4xx never."""
        suffix = f": {detail[:200]}" if detail else ""
        return cls(
            f"{channel} rejected the message (HTTP {status_code}){suffix}",
            channel=channel,
            status_code=status_code,
            retriable=status_code in (408, 425, 429) or status_code >= 500,
        )


class DeliveryUnconfirmedError(ChannelSendError):
    """``send()`` returned no message id on a channel that reports ids, so delivery is unproven.

    Deterministic provider-side failure: re-sending would risk a duplicate without a better outcome.
    """

    def __init__(self, *, channel: str = "") -> None:
        super().__init__("channel send returned no message_id", channel=channel, retriable=False)


class RateLimitError(ChannelSendError):
    """Platform rate limit hit. Always retriable with specific delay."""

    def __init__(
        self,
        message: str,
        *,
        channel: str = "",
        retry_after: float = 1.0,
        status_code: int = 429,
    ) -> None:
        super().__init__(message, channel=channel, status_code=status_code, retriable=True)
        self.retry_after = retry_after


class ChannelAuthError(ChannelError):
    """Credentials invalid or expired. Never retry — requires reconfiguration."""

    def __init__(self, message: str, *, channel: str = "") -> None:
        super().__init__(message, channel=channel)


class ChannelConnectionError(ChannelError):
    """Transport layer failure (DNS, timeout, connection reset). Always retry."""

    def __init__(self, message: str, *, channel: str = "") -> None:
        super().__init__(message, channel=channel)
