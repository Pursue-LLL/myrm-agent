"""Per-attachment delivery for providers that handle attachments one by one.

[INPUT]
- channels.core.exceptions::ChannelSendError (POS: delivery failure with partial-delivery markers)
- channels.types::MediaAttachment (POS: outbound attachment value type)

[OUTPUT]
- AttachmentAttempts: outcome of attempting every attachment (results, failed names, retriability)
- attempt_attachments(): attempt every attachment without letting one failure block the others
- deliver_attachments(): attempt every attachment, return the last id reported, then raise one error naming those that did not arrive

[POS]
A provider's ``send()`` delivers the text first, then calls ``deliver_attachments`` for the attachments.
Providers that must prepare attachments before one combined send (upload, encode) call
``attempt_attachments`` first and ``AttachmentAttempts.raise_for_failures`` after that send. One bad
attachment never blocks the others, and the single error raised lets the message bus report exactly
which attachments are missing instead of replaying (and duplicating) what the recipient already has.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.channels.core.exceptions import ChannelSendError
from app.channels.types import MediaAttachment

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class AttachmentAttempts(Generic[_T]):
    """What happened when every attachment of one message was attempted."""

    results: tuple[_T, ...]
    """Value returned for each attachment that succeeded, in message order."""
    failed: tuple[str, ...]
    """Display names of the attachments that did not make it."""
    retriable: bool
    """At least one failure may succeed on a re-send; permanent failures (unsupported type, missing file) never do."""

    def raise_for_failures(self, channel: str, *, delivered_any: bool) -> None:
        """Raise ``ChannelSendError.for_attachments`` when any attachment failed.

        ``delivered_any`` says the recipient already received something of this message (its text or other
        attachments), which makes the failure a partial delivery that is never retried or degraded.
        """
        if self.failed:
            raise ChannelSendError.for_attachments(channel, self.failed, delivered_any=delivered_any, retriable=self.retriable)


async def attempt_attachments(
    channel: str,
    media: Sequence[MediaAttachment],
    attempt: Callable[[MediaAttachment], Awaitable[_T]],
) -> AttachmentAttempts[_T]:
    """Run ``attempt`` for each attachment; a failure is recorded instead of stopping the rest."""
    results: list[_T] = []
    failed: list[str] = []
    retriable = False
    for attachment in media:
        try:
            results.append(await attempt(attachment))
        except Exception as exc:
            logger.warning("%s: attachment %s not delivered: %s", channel, attachment.display_name, exc)
            failed.append(attachment.display_name)
            retriable = retriable or not (isinstance(exc, ChannelSendError) and not exc.retriable)
    return AttachmentAttempts(tuple(results), tuple(failed), retriable)


async def deliver_attachments(
    channel: str,
    media: Sequence[MediaAttachment],
    send_one: Callable[[MediaAttachment], Awaitable[str | None]],
    *,
    text_delivered: bool,
) -> str | None:
    """Send each attachment with ``send_one``; raise ``ChannelSendError.for_attachments`` if any failed.

    Returns the id of the last attachment the platform reported one for, so an attachments-only message
    keeps a message id. ``text_delivered`` says the message text already reached the recipient, which
    makes any attachment failure a partial delivery even when every attachment failed. When every
    failure is permanent (``ChannelSendError(retriable=False)``) the error is not retriable either, so
    the bus skips straight to its text-only fallback instead of retrying attachments that cannot succeed.
    """
    attempts = await attempt_attachments(channel, media, send_one)
    attempts.raise_for_failures(channel, delivered_any=text_delivered or bool(attempts.results))
    return next((message_id for message_id in reversed(attempts.results) if message_id), None)
