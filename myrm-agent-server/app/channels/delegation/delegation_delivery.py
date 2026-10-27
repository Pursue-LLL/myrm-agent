"""Delivery of a finished delegated task to the chat it came from.

The answer a delegated task delivers is the executor's own final reply: the same
text, attachments and thread a normal chat turn would have produced. This module
only puts a one-line, localized status header in front of it.

[INPUT]
- .delegation_models::DelegationStatus, DelegationTask
- app.channels.i18n::get_text (POS: channel catalog in the sender's locale)
- app.channels.types::InboundMessage, OutboundMessage

[OUTPUT]
- build_delivery_message: The message that reports a finished task to its origin chat.

[POS]
Delivery and presentation layer for app/channels/delegation/.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.channels.i18n import get_text

from .delegation_models import DelegationStatus, DelegationTask

if TYPE_CHECKING:
    from app.channels.types import InboundMessage, OutboundMessage


def _duration_text(msg: InboundMessage, seconds: float) -> str:
    minutes, secs = divmod(max(0, round(seconds)), 60)
    if minutes:
        return get_text(msg, "delegation_duration_minutes", minutes=minutes, seconds=secs)
    return get_text(msg, "delegation_duration_seconds", seconds=secs)


def _origin_reply(task: DelegationTask, msg: InboundMessage, content: str) -> OutboundMessage:
    """A message to the chat the task came from, in the request's thread and locale."""
    reply = msg.get_or_create_correlation_context().create_reply(content, metadata={"delegation_task_id": task.task_id})
    # The task's ids carry the router's fallbacks for a message that has no chat or user id.
    return replace(reply, recipient_id=task.origin_chat_id, user_id=task.origin_user_id)


def build_delivery_message(
    task: DelegationTask,
    msg: InboundMessage,
    final_reply: OutboundMessage | None,
    snapshot: str,
) -> OutboundMessage:
    """Build the message that reports a finished task to the chat it came from.

    A completed task delivers the executor's final reply (its text, attachments and thread), or the last
    streamed snapshot when the run ended without one. A failed task delivers its member-safe failure text.
    A timed-out task delivers only the notice: whatever the cancelled run left behind is not an answer.

    Args:
        task: The finished task; its status selects the header and body.
        msg: The inbound request, which fixes the locale and the thread.
        final_reply: The executor's last reply, if the run produced one.
        snapshot: The last streamed text snapshot, used only when there is no final reply.
    """
    if task.status is DelegationStatus.TIMED_OUT:
        minutes = max(1, round(task.timeout_seconds / 60))
        return _origin_reply(task, msg, get_text(msg, "delegation_timed_out", task_id=task.task_id, minutes=minutes))

    started = task.started_at if task.started_at is not None else task.created_at
    ended = task.completed_at if task.completed_at is not None else started
    failed = task.status is DelegationStatus.FAILED
    header = get_text(
        msg,
        "delegation_failed" if failed else "delegation_done",
        task_id=task.task_id,
        duration=_duration_text(msg, ended - started),
    )

    if failed:
        body = task.error_message
    else:
        body = (final_reply.content if final_reply is not None else snapshot).strip()
        if not body and not (final_reply is not None and final_reply.media):
            body = get_text(msg, "delegation_no_output")
    content = f"{header}\n\n{body}" if body else header

    if final_reply is not None:
        return replace(final_reply, content=content)
    return _origin_reply(task, msg, content)
