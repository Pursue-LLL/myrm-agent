"""In-memory push message store for cron job notifications.

Bounded: at most ``_MAX_MESSAGES`` kept; messages older than
``_MAX_AGE_SECONDS`` are dropped on read.  Frontend deduplicates by id.

Messages are keyed by ``user_id`` to prevent cross-user data leakage.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum

_MAX_AGE_SECONDS = 120
_MAX_MESSAGES = 200


class PushLevel(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class PushMessage:
    id: str
    user_id: str
    text: str
    level: PushLevel
    job_name: str
    ts: float


_messages: list[PushMessage] = []
_lock = asyncio.Lock()


async def push(
    user_id: str,
    job_name: str,
    text: str,
    level: PushLevel = PushLevel.INFO,
) -> None:
    """Append a notification message for a specific user."""
    if not text or not user_id:
        return
    msg = PushMessage(
        id=uuid.uuid4().hex[:12],
        user_id=user_id,
        text=text,
        level=level,
        job_name=job_name,
        ts=time.time(),
    )
    async with _lock:
        _messages.append(msg)
        if len(_messages) > _MAX_MESSAGES:
            _messages.sort(key=lambda m: m.ts)
            del _messages[: len(_messages) - _MAX_MESSAGES]

    try:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        bus = get_event_bus()
        bus.publish(
            AppEvent(
                event_type=AppEventType.CRON_UPDATED,
                data={
                    "id": msg.id,
                    "text": msg.text,
                    "level": msg.level,
                    "job_name": msg.job_name,
                },
            )
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).error("Failed to emit cron push event: %s", e)


async def get_recent(
    user_id: str,
    max_age: int = _MAX_AGE_SECONDS,
) -> list[dict[str, str]]:
    """Return recent messages for a specific user, pruning expired ones."""
    cutoff = time.time() - max_age
    async with _lock:
        _messages[:] = [m for m in _messages if m.ts >= cutoff]
        return [
            {
                "id": m.id,
                "text": m.text,
                "level": m.level,
                "job_name": m.job_name,
            }
            for m in _messages
            if m.user_id == user_id
        ]
