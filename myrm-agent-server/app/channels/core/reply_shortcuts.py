"""Convenience senders built on ``BaseChannel.send``: reply to a message, or message someone proactively.

[INPUT]
- channels.types::InboundMessage, OutboundMessage (POS: channel message types)

[OUTPUT]
- ReplyShortcutsMixin: ``respond`` and ``broadcast``

[POS]
Spares callers the ``OutboundMessage`` boilerplate: ``respond`` infers channel, recipient, user and reply target from the
inbound message; ``broadcast`` is for cron and notification senders that have no inbound message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channels.types import OutboundMessage

if TYPE_CHECKING:
    from app.channels.types import InboundMessage


class ReplyShortcutsMixin:
    """``respond`` / ``broadcast`` for BaseChannel."""

    # Provided by BaseChannel; declared for type checkers only.
    name: str

    if TYPE_CHECKING:

        async def send(self, msg: OutboundMessage) -> str | None: ...

    async def respond(
        self,
        incoming_msg: InboundMessage,
        content: str,
        *,
        in_thread: bool = True,
        **kwargs: object,
    ) -> str | None:
        """Reply to an incoming message with automatic context inference.

        Convenience wrapper for send() that automatically extracts:
        - channel: from self.name
        - recipient_id: from incoming_msg.chat_id (or sender_id as fallback)
        - user_id: from incoming_msg.user_id (or sender_id as fallback)
        - reply_to_id: from incoming_msg.message_id (if in_thread=True)

        Args:
            incoming_msg: The message to reply to
            content: Reply text content
            in_thread: If True, reply in thread (uses reply_to_id)
            **kwargs: Additional OutboundMessage fields (media, metadata, etc.)

        Returns:
            Platform message_id if available, or None

        Example:
            # Before (verbose)
            await channel.send(OutboundMessage(
                channel="slack",
                recipient_id=incoming_msg.chat_id,
                reply_to_id=incoming_msg.message_id,
                content="Hello!",
                user_id=incoming_msg.user_id
            ))

            # After (concise)
            await channel.respond(incoming_msg, "Hello!")
        """
        return await self.send(
            OutboundMessage(
                channel=self.name,
                recipient_id=incoming_msg.chat_id or incoming_msg.sender_id,
                content=content,
                user_id=incoming_msg.user_id or incoming_msg.sender_id,
                reply_to_id=incoming_msg.message_id if in_thread else None,
                **kwargs,  # type: ignore[arg-type]
            )
        )

    async def broadcast(
        self,
        recipient_id: str,
        content: str,
        user_id: str,
        *,
        thread_ts: str | None = None,
        **kwargs: object,
    ) -> str | None:
        """Send a proactive message to a channel or user.

        Convenience wrapper for send() for proactive messaging scenarios
        (cron jobs, notifications, alerts). Requires explicit user_id since
        it cannot be inferred from context.

        Args:
            recipient_id: Target channel_id or user_id
            content: Message text content
            user_id: User ID for audit/authorization (required)
            thread_ts: Optional thread timestamp (Slack-specific)
            **kwargs: Additional OutboundMessage fields (media, metadata, etc.)

        Returns:
            Platform message_id if available, or None

        Example:
            # Before (verbose)
            await channel.send(OutboundMessage(
                channel="slack",
                recipient_id="C12345",
                content="Cron job completed!",
                user_id=job.user_id,
                metadata={"job_name": "daily_report"}
            ))

            # After (concise)
            await channel.broadcast(
                "C12345",
                "Cron job completed!",
                user_id=job.user_id,
                metadata={"job_name": "daily_report"}
            )
        """
        raw_metadata = kwargs.pop("metadata", None)
        metadata: dict[str, object] = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        if thread_ts:
            metadata["thread_ts"] = thread_ts

        return await self.send(
            OutboundMessage(
                channel=self.name,
                recipient_id=recipient_id,
                content=content,
                user_id=user_id,
                metadata=metadata or None,
                **kwargs,  # type: ignore[arg-type]
            )
        )
