"""Desktop approval registry — pending requests, settlement, and decision audit.

[INPUT]
- myrm_agent_harness.toolkits.computer_use.types::ForegroundPermissionResult, ForegroundPermissionScope

[OUTPUT]
- DesktopApprovalRegistry: class-level pending approval registry with
  settlement semantics (resolved | expired | missing) and decision audit
- approval_fingerprint: stable execution fingerprint binding one approval
  to one operation plus trust key
- resolve_desktop_control_approval(_status): settlement entry points with
  first-settlement rule

[POS]
Server-layer approval ledger. Owns pending lifecycle, bounded registries,
and the decision audit consumed by diagnostics; authorization policy lives
in gate.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import TypedDict

from myrm_agent_harness.core.events.types import AgentEventType
from myrm_agent_harness.toolkits.computer_use.types import (
    ForegroundPermissionResult,
    ForegroundPermissionScope,
)

logger = logging.getLogger(__name__)

_APPROVAL_DIR = ".agent/desktop_control"
_APPROVAL_FILE = "approved_apps.json"
_DENY_FILE = "denied_apps.json"
# Registry bounds; the registry sheds load fail-closed at capacity.
_MAX_PENDING = 200
_TOMBSTONE_MAX = 500
_TOMBSTONE_TTL_SEC = 600.0
_DECISIONS_MAX = 50
_TEST_SEED_TTL_SEC = 120.0
# Window in which a same-app request with a new fingerprint flags drift.
_GRANT_CHANGE_WINDOW_SEC = 300.0
_REASON_MAX_LEN = 500


def approval_fingerprint(*, operation: str, trust_key: str) -> str:
    """Stable execution fingerprint binding one approval to one operation.

    Only stable identity participates: the app trust key plus the requested
    operation. Volatile presentation (window title, reason text) stays out,
    keeping legitimate re-prompts stable.
    """
    digest = hashlib.sha1(
        f"{operation.strip()}\0{trust_key.strip()}".encode("utf-8"),
        usedforsecurity=False,
    )
    return digest.hexdigest()[:16]


def deny_key_for(*, trust_key: str, fingerprint: str) -> str:
    """Session-denial key scoping one refusal to one trust key plus one operation."""
    return f"{trust_key}\0{fingerprint}"


def grant_changed_since(
    last: tuple[str, float] | None, *, fingerprint: str, now: float, window_sec: float = _GRANT_CHANGE_WINDOW_SEC
) -> bool:
    """Whether a same-app request drifts from the last recorded grant.

    The approval card surfaces this flag so the user re-confirms a changed
    target.
    """
    if last is None:
        return False
    last_fingerprint, granted_at = last
    return last_fingerprint != fingerprint and now - granted_at <= window_sec


async def emit_withdraw_card(sink: object, *, request_id: str) -> None:
    """Best-effort withdraw card so stale approval banners clear.

    Reuses the approval-request event with a withdrawn flag: clients unaware
    of the flag render it as a duplicate request, clients aware of it clear
    the matching banner.
    """
    try:
        await sink.emit(  # type: ignore[union-attr]
            {
                "type": AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST,
                "data": {"request_id": request_id, "withdrawn": True},
            }
        )
    except Exception as exc:
        logger.debug("Desktop approval withdraw emit failed: %s", exc)


@dataclass(slots=True)
class _PendingApproval:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    result: ForegroundPermissionResult | None = None
    # Request metadata for observability and grant binding, populated at
    # creation. Authorization decisions never rely on these fields alone.
    created_at: float = 0.0
    reason: str = ""
    operation: str = ""
    app_name: str = ""
    window_title: str = ""
    app_id: str = ""
    fingerprint: str = ""
    test_only: bool = False
    # Settlement provenance: "user" (explicit resolve), "recovery" (dev
    # reset), "" (undecided/timeout). Durable denials require "user".
    decided_by: str = ""
    deny_reason: str = ""


class _ApprovalDecision(TypedDict):
    request_id: str
    trust_key: str
    fingerprint: str
    operation: str
    decision: str
    scope: str
    reason: str
    timestamp: float


class DesktopApprovalRegistry:
    """In-memory pending desktop approval requests keyed by request_id."""

    _pending: dict[str, _PendingApproval] = {}
    # Settled-without-decision markers (timeout or cap eviction), bounded
    # with TTL; resolve-after-timeout reports "expired", unknown ids "missing".
    _tombstones: dict[str, float] = {}
    _decisions: deque[_ApprovalDecision] = deque(maxlen=_DECISIONS_MAX)

    @classmethod
    def create(
        cls,
        *,
        reason: str = "",
        operation: str = "",
        app_name: str = "",
        window_title: str = "",
        app_id: str = "",
        fingerprint: str = "",
        test_only: bool = False,
    ) -> tuple[str, _PendingApproval]:
        now = time.monotonic()
        cls._sweep_test_only(now)
        if len(cls._pending) >= _MAX_PENDING:
            # At capacity the oldest undecided request is dropped denied.
            oldest_id = min(cls._pending, key=lambda rid: cls._pending[rid].created_at)
            cls._settle_timeout(oldest_id)
            logger.warning("Desktop approval registry full: evicted oldest pending request")
        request_id = uuid.uuid4().hex
        pending = _PendingApproval(
            created_at=now,
            reason=reason,
            operation=operation,
            app_name=app_name,
            window_title=window_title,
            app_id=app_id,
            fingerprint=fingerprint,
            test_only=test_only,
        )
        cls._pending[request_id] = pending
        return request_id, pending

    @classmethod
    def _sweep_test_only(cls, now: float) -> None:
        stale = [
            rid for rid, pending in cls._pending.items() if pending.test_only and now - pending.created_at > _TEST_SEED_TTL_SEC
        ]
        for rid in stale:
            cls._settle_timeout(rid)

    @classmethod
    def _settle_timeout(cls, request_id: str) -> bool:
        """Drop a pending request without a user decision (timeout/eviction).

        Returns True only when this call settled a live entry (first
        settlement wins: a user decision racing the deadline is preserved).
        """
        pending = cls._pending.pop(request_id, None)
        if pending is None:
            return False
        if len(cls._tombstones) >= _TOMBSTONE_MAX:
            oldest = min(cls._tombstones, key=lambda rid: cls._tombstones[rid])
            cls._tombstones.pop(oldest, None)
        cls._tombstones[request_id] = time.monotonic()
        pending.event.set()
        return True

    @classmethod
    def resolve(
        cls,
        request_id: str,
        *,
        granted: bool,
        scope: ForegroundPermissionScope,
        reason: str = "",
    ) -> bool:
        pending = cls._pending.pop(request_id, None)
        if pending is None:
            return False
        pending.result = ForegroundPermissionResult(granted=granted, scope=scope)
        pending.decided_by = "user"
        if not granted and reason.strip():
            pending.deny_reason = reason.strip()[:_REASON_MAX_LEN]
        pending.event.set()
        return True

    @classmethod
    def resolve_status(
        cls,
        request_id: str,
        *,
        granted: bool,
        scope: ForegroundPermissionScope,
        reason: str = "",
    ) -> str:
        """Resolve with settlement semantics: resolved | expired | missing."""
        if cls.resolve(request_id, granted=granted, scope=scope, reason=reason):
            return "resolved"
        now = time.monotonic()
        settled_at = cls._tombstones.get(request_id)
        if settled_at is not None and now - settled_at <= _TOMBSTONE_TTL_SEC:
            return "expired"
        return "missing"

    @classmethod
    def record_decision(
        cls,
        *,
        request_id: str,
        trust_key: str,
        fingerprint: str,
        operation: str,
        decision: str,
        scope: str = "",
        reason: str = "",
    ) -> None:
        cls._decisions.append(
            {
                "request_id": request_id,
                "trust_key": trust_key,
                "fingerprint": fingerprint,
                "operation": operation,
                "decision": decision,
                "scope": scope,
                "reason": reason[:_REASON_MAX_LEN],
                "timestamp": time.time(),
            }
        )

    @classmethod
    def decision_snapshot(cls) -> list[dict[str, object]]:
        return [dict(entry) for entry in cls._decisions]

    @classmethod
    def pending_snapshot(cls) -> list[str]:
        return list(cls._pending.keys())

    @classmethod
    def pending_details(cls) -> list[dict[str, object]]:
        return [
            {
                "request_id": request_id,
                "app_name": pending.app_name,
                "operation": pending.operation,
                "fingerprint": pending.fingerprint,
                "created_at": pending.created_at,
                "test_only": pending.test_only,
            }
            for request_id, pending in cls._pending.items()
        ]

    @classmethod
    def clear_all(cls) -> None:
        """Deny and drop all in-memory pending approvals (E2E/dev recovery)."""
        for pending in cls._pending.values():
            if pending.result is None:
                pending.result = ForegroundPermissionResult(
                    granted=False,
                    scope=ForegroundPermissionScope.once,
                )
                pending.decided_by = "recovery"
            pending.event.set()
        cls._pending.clear()


def resolve_desktop_control_approval(
    request_id: str,
    *,
    granted: bool,
    scope: str = "once",
    reason: str = "",
) -> bool:
    """Resolve one pending approval; True only on first settlement."""
    try:
        scope_enum = ForegroundPermissionScope(scope)
    except ValueError:
        scope_enum = ForegroundPermissionScope.once
    return DesktopApprovalRegistry.resolve(request_id, granted=granted, scope=scope_enum, reason=reason)


def resolve_desktop_control_approval_status(
    request_id: str,
    *,
    granted: bool,
    scope: str = "once",
    reason: str = "",
) -> str:
    """Resolve with settlement semantics: resolved | expired | missing."""
    try:
        scope_enum = ForegroundPermissionScope(scope)
    except ValueError:
        scope_enum = ForegroundPermissionScope.once
    return DesktopApprovalRegistry.resolve_status(request_id, granted=granted, scope=scope_enum, reason=reason)
