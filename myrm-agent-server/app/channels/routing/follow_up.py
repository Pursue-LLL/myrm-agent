"""Proactive follow-up decisions for group turns — pure mapping layer.

Covers the delivery leg of team-shared follow-up: completion receipts for
finished long/delegated work, stall nudges for quiet threads with pending
items, and idempotent send guards. Trigger sources (commitment store,
approval/draft pending counts) are queried by callers; this module only
decides, never touches DB, LLM, or network — zero prompt-cache impact.

[INPUT]
- channels.types::TopicContext (POS: follow-up policy fields)
- myrm_agent_harness cooldown patterns (POS: BoundedCooldownMap precedent)

[OUTPUT]
- FollowUpDecision: receipt/nudge verdicts + dedup keys.
- should_post_receipt / should_nudge_stall: pure predicates.
- FollowUpDedup: bounded TTL dedup registry.

[POS]
Deterministic follow-up policy for channel turns. Sibling to
identity_scope.py (compartment) and policy_resolver_support.py (gating).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

COMPLETION_RECEIPT_MIN_SECONDS = 300.0
STALL_AFTER_SECONDS = 48.0 * 3600.0
NUDGE_COOLDOWN_SECONDS = 24.0 * 3600.0
_DEDUP_MAX_SIZE = 2000
_TRACKER_MAX_SIZE = 1000


@dataclass(frozen=True, slots=True)
class FollowUpDecision:
    """Verdict for one proactive follow-up opportunity."""

    post_receipt: bool = False
    post_nudge: bool = False
    dedup_key: str = ""


class FollowUpDedup:
    """Bounded TTL registry preventing duplicate proactive sends.

    Keys expire after ``ttl_seconds`` so a genuinely re-stalled thread can
    be nudged again later, while crash retries within the window collapse.
    """

    def __init__(self, ttl_seconds: float = NUDGE_COOLDOWN_SECONDS, max_size: int = _DEDUP_MAX_SIZE) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._entries: dict[str, float] = {}

    def seen(self, key: str) -> bool:
        """Return True when key was marked within the TTL window."""
        now = time.monotonic()
        stamped = self._entries.get(key)
        if stamped is None:
            return False
        if now - stamped > self._ttl:
            self._entries.pop(key, None)
            return False
        return True

    def mark(self, key: str) -> None:
        """Record a send; evicts oldest entry when over capacity."""
        if len(self._entries) >= self._max_size:
            oldest = min(self._entries, key=lambda k: self._entries[k])
            self._entries.pop(oldest, None)
        self._entries[key] = time.monotonic()


def should_post_receipt(
    *,
    is_group: bool,
    receipts_enabled: bool,
    identity_revoked: bool,
    turn_seconds: float,
    is_resume: bool,
    result_sent: bool,
    min_seconds: float = COMPLETION_RECEIPT_MIN_SECONDS,
) -> bool:
    """Decide whether a finished turn deserves a completion receipt post."""
    if not is_group or not receipts_enabled or identity_revoked or not result_sent:
        return False
    return is_resume or turn_seconds >= min_seconds


def should_nudge_stall(
    *,
    stall_enabled: bool,
    identity_revoked: bool,
    muted: bool,
    silent_seconds: float,
    has_pending: bool,
    cooldown_ok: bool,
    stall_after_seconds: float = STALL_AFTER_SECONDS,
) -> bool:
    """Decide whether a quiet thread deserves one proactive nudge."""
    if not stall_enabled or identity_revoked or muted or not has_pending or not cooldown_ok:
        return False
    return silent_seconds >= stall_after_seconds


@dataclass(frozen=True, slots=True)
class TrackedThread:
    """A group thread candidate for stall evaluation."""

    channel: str
    chat_id: str
    thread_id: str | None
    requester_id: str
    requester_name: str | None
    locale: str


class ThreadStallTracker:
    """Bounded registry of group threads with activity + requester context.

    Slots carry routing coordinates so a lazy scan can resolve each
    candidate's follow-up policy without extra bookkeeping elsewhere.
    """

    def __init__(self, max_size: int = _TRACKER_MAX_SIZE) -> None:
        self._max_size = max_size
        self._slots: dict[str, TrackedThread] = {}
        self._active: dict[str, float] = {}
        self._muted: set[str] = set()

    @staticmethod
    def thread_key(channel: str, chat_id: str, thread_id: str | None) -> str:
        """Stable storage key shared by touch/scan paths."""
        return f"{channel}:{chat_id}:{thread_id or ''}"

    def touch(self, slot: TrackedThread) -> None:
        """Record activity now, evicting the oldest entry when over capacity.

        Muted threads stay muted: activity refreshes nothing for them.
        """
        key = self.thread_key(slot.channel, slot.chat_id, slot.thread_id)
        if key in self._muted:
            return
        if len(self._slots) >= self._max_size:
            oldest = min(self._active, key=lambda k: self._active.get(k, 0.0))
            self._slots.pop(oldest, None)
            self._active.pop(oldest, None)
            self._muted.discard(oldest)
        self._slots[key] = slot
        self._active[key] = time.monotonic()

    def stalled(self, stall_after_seconds: float = STALL_AFTER_SECONDS) -> list[tuple[str, TrackedThread]]:
        """Return (key, slot) pairs silent beyond the stall threshold."""
        now = time.monotonic()
        return [
            (key, slot)
            for key, slot in self._slots.items()
            if key not in self._muted and now - self._active.get(key, now) >= stall_after_seconds
        ]

    def refresh(self, key: str) -> None:
        """Reset a thread's clock after a nudge (starts the cooldown)."""
        if key in self._slots:
            self._active[key] = time.monotonic()

    def drop(self, key: str) -> None:
        """Forget a thread (unbind or policy disabled). Clears mute as well."""
        self._slots.pop(key, None)
        self._active.pop(key, None)
        self._muted.discard(key)

    def mute(self, key: str) -> None:
        """Silence a thread until unbound. Muted threads are never nudged."""
        if key in self._slots:
            self._muted.add(key)

    def is_muted(self, key: str) -> bool:
        """Return True when the thread was explicitly muted."""
        return key in self._muted


_dedup: FollowUpDedup | None = None
_stall_tracker: ThreadStallTracker | None = None


def get_follow_up_dedup() -> FollowUpDedup:
    """Process-wide dedup registry (mirrors ApprovalTimeoutScheduler.get)."""
    global _dedup
    if _dedup is None:
        _dedup = FollowUpDedup()
    return _dedup


def get_stall_tracker() -> ThreadStallTracker:
    """Process-wide stall registry (mirrors ApprovalTimeoutScheduler.get)."""
    global _stall_tracker
    if _stall_tracker is None:
        _stall_tracker = ThreadStallTracker()
    return _stall_tracker


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


async def maybe_post_completion_receipt(
    *,
    bus: object,
    topic: object | None,
    msg: object,
    chat_id: str,
    elapsed_seconds: float,
    is_resume: bool,
    delivered: bool,
    record_outbound: object | None = None,
) -> bool:
    """Post a completion receipt in the origin thread when warranted.

    Pure policy gate + best-effort send. Returns True when posted. Draft-held
    turns are skipped (approval covers review); failures never propagate.
    """
    try:
        from app.channels.i18n import get_text
        from app.channels.types import InboundMessage, OutboundMessage, ReplyMode

        assert isinstance(msg, InboundMessage)
        receipts_on = True if topic is None else bool(getattr(topic, "completion_receipts", True))
        revoked = bool(getattr(topic, "identity_revoked", False)) if topic is not None else False
        draft_held = False
        if topic is not None:
            draft_held = getattr(topic, "reply_mode", None) == ReplyMode.DRAFT_REVIEW
        if not should_post_receipt(
            is_group=msg.is_group,
            receipts_enabled=receipts_on,
            identity_revoked=revoked,
            turn_seconds=elapsed_seconds,
            is_resume=is_resume,
            result_sent=delivered and not draft_held,
        ):
            return False

        trigger_id = msg.message_id or f"elapsed-{int(elapsed_seconds // 60)}"
        dedup_key = f"receipt:{msg.channel}:{chat_id}:{msg.thread_id or ''}:{trigger_id}"
        dedup = get_follow_up_dedup()
        if dedup.seen(dedup_key):
            return False

        content = get_text(msg, "followup_receipt_done", elapsed=_format_elapsed(elapsed_seconds))
        out = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=msg.message_id if msg.is_group else None,
            metadata={"proactive": True, "followup_kind": "completion_receipt"},
        )
        await bus.publish_outbound(out)  # type: ignore[attr-defined]
        dedup.mark(dedup_key)
        note_group_activity(
            msg.channel, chat_id, msg.thread_id, msg.sender_id, msg.sender_name, _locale_of(msg)
        )
        if record_outbound is not None:
            await record_outbound(  # type: ignore[operator]
                channel=msg.channel, chat_id=chat_id, content=content, thread_id=msg.thread_id
            )
        return True
    except Exception:
        logger.warning("Completion receipt skipped for %s", chat_id, exc_info=True)
        return False


def note_group_activity(
    channel: str, chat_id: str, thread_id: str | None, requester_id: str, requester_name: str | None, locale: str
) -> None:
    """Record group activity for stall tracking (never raises)."""
    try:
        get_stall_tracker().touch(
            TrackedThread(
                channel=channel, chat_id=chat_id, thread_id=thread_id,
                requester_id=requester_id, requester_name=requester_name, locale=locale,
            )
        )
    except Exception:
        logger.warning("Stall tracker touch skipped", exc_info=True)


def drop_tracked_thread(channel: str, chat_id: str, thread_id: str | None) -> None:
    """Forget a thread (unbind). Never raises."""
    try:
        get_stall_tracker().drop(ThreadStallTracker.thread_key(channel, chat_id, thread_id))
    except Exception:
        logger.warning("Stall tracker drop skipped", exc_info=True)


def mute_tracked_thread(channel: str, chat_id: str, thread_id: str | None) -> None:
    """Mute a thread until unbound. Muted threads are never nudged. Never raises."""
    try:
        get_stall_tracker().mute(ThreadStallTracker.thread_key(channel, chat_id, thread_id))
    except Exception:
        logger.warning("Stall tracker mute skipped", exc_info=True)


def _locale_of(msg: object) -> str:
    try:
        from app.channels.i18n import resolve_message_locale

        return str(resolve_message_locale(msg))  # type: ignore[arg-type]
    except Exception:
        return "en"


async def scan_stalled_threads(
    *,
    bus: object,
    resolve_topic: object,
    record_outbound: object | None = None,
) -> int:
    """Lazily nudge stalled group threads with pending items. Returns nudged count.

    Called fire-and-forget from the inbound loop; never raises. Each nudge
    requires an explicit pending signal (open approvals/drafts for the chat)
    so settled threads stay silent.
    """
    nudged = 0
    try:
        from app.channels.i18n import channel_t
        from app.channels.types import OutboundMessage
        from app.services.approvals.registry import ApprovalRegistry

        tracker = get_stall_tracker()
        dedup = get_follow_up_dedup()
        for key, slot in tracker.stalled():
            try:
                topic = await resolve_topic(slot.channel, slot.chat_id, slot.thread_id)  # type: ignore[operator]
                stall_on = bool(getattr(topic, "stall_nudge", False)) if topic is not None else False
                revoked = bool(getattr(topic, "identity_revoked", False)) if topic is not None else False
                pending = 0
                try:
                    pending = await ApprovalRegistry.count_pending_for_chat(slot.chat_id)
                except Exception:
                    pending = 0
                if not should_nudge_stall(
                    stall_enabled=stall_on,
                    identity_revoked=revoked,
                    muted=False,
                    silent_seconds=STALL_AFTER_SECONDS,
                    has_pending=pending > 0,
                    cooldown_ok=not dedup.seen(f"nudge:{key}"),
                ):
                    continue

                mention = f"@{slot.requester_name or slot.requester_id} " if slot.requester_id else ""
                content = str(
                    channel_t(
                        slot.locale or "en",
                        "followup_stall_nudge",
                        mention=mention,
                    )
                )
                out = OutboundMessage(
                    channel=slot.channel,
                    recipient_id=slot.chat_id,
                    content=content,
                    user_id=slot.requester_id,
                    thread_id=slot.thread_id,
                    metadata={"proactive": True, "followup_kind": "stall_nudge"},
                )
                await bus.publish_outbound(out)  # type: ignore[attr-defined]
                dedup.mark(f"nudge:{key}")
                tracker.refresh(key)
                if record_outbound is not None:
                    await record_outbound(  # type: ignore[operator]
                        channel=slot.channel, chat_id=slot.chat_id, content=content, thread_id=slot.thread_id
                    )
                nudged += 1
            except Exception:
                logger.warning("Stall scan skipped thread %s", key, exc_info=True)
                continue
    except Exception:
        logger.warning("Stall scan aborted", exc_info=True)
    return nudged
