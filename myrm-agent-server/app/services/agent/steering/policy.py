"""Steering policy mode — quoted-reply preservation in front of the transport.

[INPUT]
- myrm_agent_harness.agent.orchestration.steering::SteeringQueue (POS: Bounded
  inbound steering queue with dedup, envelope, metrics and snapshots.)
- app.services.agent.steering_registry::SteeringRegistry (POS: Session-level
  SteeringToken registry bridging HTTP endpoints and running sessions.)

[OUTPUT]
- policy_steer: opt-in enqueue with dedup, size cap, envelope and metrics.
- policy_metrics: per-chat operational counters for observability.

[POS]
Server business layer (single-machine, per-sandbox). Policy adapter over the
harness queue and the existing transport registry. Does not change direct
steer/redirect semantics; policy mode is strictly opt-in per request.
"""

from __future__ import annotations

import logging
import threading
from typing import Literal, TypedDict

from myrm_agent_harness.agent.orchestration.steering import (
    MAX_NOTE_CHARS,
    SteeringQueue,
    drain_into_token,
)

from app.services.agent.steering_registry import SteeringRegistry

logger = logging.getLogger(__name__)


class PolicySteerOutcome(TypedDict):
    """Machine-readable outcome of one policy-mode steer call."""

    status: Literal["injected", "deduped", "too_large", "no_active"]
    injected: int
    deduped: bool
    metrics: dict[str, int]


_lock = threading.Lock()
_queues: dict[str, SteeringQueue] = {}


def _queue_for(chat_id: str) -> SteeringQueue:
    """Return the per-chat policy queue, creating it on first use."""
    with _lock:
        queue = _queues.get(chat_id)
        if queue is None:
            queue = SteeringQueue()
            _queues[chat_id] = queue
        return queue


def policy_steer(chat_id: str, message: str, quoted_ref: str | None = None) -> PolicySteerOutcome:
    """Enqueue with policy (dedup, size cap, envelope, metrics) and inject.

    Returns ``no_active`` when no running session exists, ``too_large`` when
    the body exceeds the cap, ``deduped`` for repeat submits, else
    ``injected`` with the drained count and current counters.
    """
    body = message.strip()
    if len(body) > MAX_NOTE_CHARS:
        return {"status": "too_large", "injected": 0, "deduped": False, "metrics": _metrics_of(chat_id)}
    token = SteeringRegistry.get_token(chat_id)
    if token is None:
        return {"status": "no_active", "injected": 0, "deduped": False, "metrics": _metrics_of(chat_id)}
    queue = _queue_for(chat_id)
    already_queued = any(note.text == body for note in queue.pending(chat_id))
    note = queue.enqueue(chat_id, body, quoted_ref=quoted_ref)
    injected = drain_into_token(queue, token, chat_id)
    after = queue.metrics_snapshot()
    deduped = already_queued
    logger.info(
        "Policy steer: chat_id=%s note_id=%s injected=%d deduped=%s",
        chat_id,
        note.note_id,
        injected,
        deduped,
    )
    return {"status": "deduped" if deduped else "injected", "injected": injected, "deduped": deduped, "metrics": after.to_dict()}


def policy_metrics(chat_id: str) -> dict[str, int]:
    """Return the per-chat policy counters (zeros when never used)."""
    return _metrics_of(chat_id)


def _metrics_of(chat_id: str) -> dict[str, int]:
    """Read counters without creating queue state."""
    with _lock:
        queue = _queues.get(chat_id)
    if queue is None:
        return {"received": 0, "dedup_dropped": 0, "evicted": 0, "injected": 0}
    return queue.metrics_snapshot().to_dict()


def reset_for_tests() -> None:
    """Clear per-chat policy queues (tests only)."""
    with _lock:
        _queues.clear()
