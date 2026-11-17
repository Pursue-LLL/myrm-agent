"""In-process RunDigest SSOT for Co-Pilot Run Observer.

[INPUT]
- StreamContentCollector progress steps (via stream_collector hook)
- ApprovalRegistry pending counts (async refresh)

[OUTPUT]
- RunDigestStore: get/update/clear per chat_id + SSE publish; terminal_failures lists chats whose last run failed or was cancelled
- RunSession: the live run of a chat, returned by begin_run so that the turn which began a run is the one that ends it

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
class RunSession:
    started_at: float
    phase: RunDigestPhase = RunDigestPhase.RUNNING
    pending_approval_count: int = 0
    progress_steps: list[dict[str, object]] = field(default_factory=list)


class RunDigestStore:
    """Process-local run digest registry keyed by chat_id."""

    _digests: dict[str, RunDigest] = {}
    _sessions: dict[str, RunSession] = {}

    @classmethod
    def begin_run(cls, chat_id: str) -> RunSession | None:
        """Start the chat's run as the live one and return its handle; None for a turn without a chat."""
        if not chat_id:
            return None
        run = RunSession(started_at=time.monotonic())
        cls._sessions[chat_id] = run
        cls._publish(chat_id, RunDigestPhase.RUNNING, [])
        return run

    @classmethod
    def end_run(
        cls,
        chat_id: str,
        *,
        phase: RunDigestPhase = RunDigestPhase.COMPLETED,
        progress_steps: list[dict[str, object]] | None = None,
        run: RunSession | None = None,
    ) -> bool:
        """End the chat's live run and publish its final digest; False when `run` is no longer the live run.

        A turn passes the handle `begin_run` gave it, so a turn that ends late neither closes the run of the turn that
        started after it nor closes its own run twice. Without a handle, whichever run is live ends.
        """
        if not chat_id:
            return False
        session = cls._sessions.get(chat_id)
        if run is not None and session is not run:
            return False
        cls._sessions.pop(chat_id, None)
        steps = progress_steps or []
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
        return True

    @classmethod
    def clear(cls, chat_id: str) -> None:
        cls._sessions.pop(chat_id, None)
        cls._digests.pop(chat_id, None)

    @classmethod
    def get(cls, chat_id: str) -> RunDigest | None:
        return cls._digests.get(chat_id)

    @classmethod
    def terminal_failures(cls) -> list[RunDigest]:
        """Digests whose latest run ended in error or cancellation (a new run replaces its chat's digest)."""
        failed = (RunDigestPhase.ERROR, RunDigestPhase.CANCELLED)
        return [digest for digest in cls._digests.values() if digest.phase in failed]

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
            session = RunSession(started_at=time.monotonic())
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
            session = RunSession(started_at=time.monotonic())
            cls._sessions[chat_id] = session
        session.pending_approval_count = max(0, count)
        phase = RunDigestPhase.WAITING_APPROVAL if session.pending_approval_count > 0 else RunDigestPhase.RUNNING
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


__all__ = ["RunDigestStore", "RunSession"]
