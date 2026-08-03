"""In-process RunDigest SSOT for Co-Pilot Run Observer.

[INPUT]
- StreamContentCollector progress steps (via stream_collector hook)
- ApprovalRegistry pending counts (async refresh)

[OUTPUT]
- RunDigestStore: get/update/clear per chat_id + SSE publish

[POS]
Business-layer copilot run observation. Not harness; not control plane.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from myrm_agent_harness.agent.streaming.run_digest import (
    RunDigest,
    RunDigestPhase,
    build_run_digest,
)

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _RunSession:
    started_at: float
    phase: RunDigestPhase = RunDigestPhase.RUNNING
    pending_approval_count: int = 0
    progress_steps: list[dict[str, object]] = field(default_factory=list)


class RunDigestStore:
    """Process-local run digest registry keyed by chat_id."""

    _digests: dict[str, RunDigest] = {}
    _sessions: dict[str, _RunSession] = {}

    @classmethod
    def begin_run(cls, chat_id: str) -> None:
        if not chat_id:
            return
        cls._sessions[chat_id] = _RunSession(started_at=time.monotonic())
        cls._publish(chat_id, RunDigestPhase.RUNNING, [])

    @classmethod
    def end_run(
        cls,
        chat_id: str,
        *,
        phase: RunDigestPhase = RunDigestPhase.COMPLETED,
        progress_steps: list[dict[str, object]] | None = None,
    ) -> None:
        if not chat_id:
            return
        steps = progress_steps or []
        session = cls._sessions.pop(chat_id, None)
        elapsed = 0
        if session is not None:
            elapsed = int(time.monotonic() - session.started_at)
        digest = build_run_digest(
            chat_id=chat_id,
            progress_steps=steps,
            phase=phase,
            pending_approval_count=0,
            elapsed_seconds=elapsed,
        )
        cls._digests[chat_id] = digest
        cls._emit(digest)

    @classmethod
    def clear(cls, chat_id: str) -> None:
        cls._sessions.pop(chat_id, None)
        cls._digests.pop(chat_id, None)

    @classmethod
    def get(cls, chat_id: str) -> RunDigest | None:
        return cls._digests.get(chat_id)

    @classmethod
    def update_from_progress(
        cls,
        chat_id: str,
        progress_steps: list[dict[str, object]],
        *,
        pending_approval_count: int | None = None,
    ) -> None:
        if not chat_id:
            return
        session = cls._sessions.get(chat_id)
        if session is None:
            session = _RunSession(started_at=time.monotonic())
            cls._sessions[chat_id] = session
        session.progress_steps = list(progress_steps)
        if pending_approval_count is not None:
            session.pending_approval_count = pending_approval_count
        phase = RunDigestPhase.RUNNING
        if session.pending_approval_count > 0:
            phase = RunDigestPhase.WAITING_APPROVAL
        cls._publish(
            chat_id,
            phase,
            session.progress_steps,
            pending_approval_count=session.pending_approval_count,
            elapsed_seconds=int(time.monotonic() - session.started_at),
        )

    @classmethod
    def set_pending_approval_count(cls, chat_id: str, count: int) -> None:
        session = cls._sessions.get(chat_id)
        if session is None and count <= 0:
            return
        if session is None:
            session = _RunSession(started_at=time.monotonic())
            cls._sessions[chat_id] = session
        session.pending_approval_count = max(0, count)
        phase = (
            RunDigestPhase.WAITING_APPROVAL
            if session.pending_approval_count > 0
            else RunDigestPhase.RUNNING
        )
        cls._publish(
            chat_id,
            phase,
            session.progress_steps,
            pending_approval_count=session.pending_approval_count,
            elapsed_seconds=int(time.monotonic() - session.started_at),
        )

    @classmethod
    def _publish(
        cls,
        chat_id: str,
        phase: RunDigestPhase,
        progress_steps: list[dict[str, object]],
        *,
        pending_approval_count: int = 0,
        elapsed_seconds: int = 0,
    ) -> None:
        digest = build_run_digest(
            chat_id=chat_id,
            progress_steps=progress_steps,
            phase=phase,
            pending_approval_count=pending_approval_count,
            elapsed_seconds=elapsed_seconds,
        )
        cls._digests[chat_id] = digest
        cls._emit(digest)

    @classmethod
    def _emit(cls, digest: RunDigest) -> None:
        try:
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.RUN_DIGEST_UPDATED,
                    data={"chat_id": digest.chat_id, "digest": digest.to_dict()},
                )
            )
        except Exception as exc:
            logger.warning("Failed to publish run digest SSE: %s", exc)


__all__ = ["RunDigestStore"]
