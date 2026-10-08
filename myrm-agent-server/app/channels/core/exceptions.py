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
- ChannelSendError: Message delivery failed. May be retriable depending on st...
- DeliveryUnconfirmedError: send() returned no message id on a channel that reports ids.
- RateLimitError: Platform rate limit hit. Always retriable with specific d...
- ChannelAuthError: Credentials invalid or expired. Never retry — requires re...
- ChannelConnectionError: Transport layer failure (DNS, timeout, connection reset)....

[POS]
Channel exception hierarchy for precise retry and error handling.
"""

from __future__ import annotations


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
    already received. ``failed_attachments`` names the attachments that did not arrive.
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
        self.retriable = retriable
        self.accepted = accepted
        self.failed_attachments = failed_attachments


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
