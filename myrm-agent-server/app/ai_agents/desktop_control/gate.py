"""Desktop control gate — per-app approval and foreground permission.

[INPUT]
- myrm_agent_harness.toolkits.computer_use.types::ForegroundPermissionResult, ForegroundPermissionScope
- myrm_agent_harness.toolkits.computer_use.app_identity::resolve_trust_key, trust_key_matches
- myrm_agent_harness.core.events.types::AgentEventType
- myrm_agent_harness.utils.runtime.progress_sink::get_tool_progress_sink

[OUTPUT]
- DesktopControlGate: async callback for foreground permission requests
- DesktopApprovalRegistry: class-level pending approval registry
- resolve_desktop_control_approval: resolve pending approval by request_id

[POS]
Server-layer gate that bridges harness ForegroundPermissionCallback with
frontend approval UI via SSE events. Manages per-app approval persistence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
import weakref
from collections import deque
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from myrm_agent_harness.core.events.types import AgentEventType
from myrm_agent_harness.toolkits.computer_use.app_identity import (
    resolve_trust_key,
    trust_key_matches,
)
from myrm_agent_harness.toolkits.computer_use.types import (
    ForegroundPermissionResult,
    ForegroundPermissionScope,
)
from myrm_agent_harness.utils.runtime.progress_sink import get_tool_progress_sink

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SEC = 60.0
_raw_timeout = os.getenv("MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC", "60").strip()
try:
    _parsed_timeout = float(_raw_timeout)
except ValueError:
    _parsed_timeout = _DEFAULT_TIMEOUT_SEC
_DEFAULT_TIMEOUT_SEC = max(5.0, _parsed_timeout)
_APPROVAL_DIR = ".agent/desktop_control"
_APPROVAL_FILE = "approved_apps.json"
_DENY_FILE = "denied_apps.json"
# Bounded registries: fail closed instead of growing without limit.
_MAX_PENDING = 200
_TOMBSTONE_MAX = 500
_TOMBSTONE_TTL_SEC = 600.0
_DECISIONS_MAX = 50
_TEST_SEED_TTL_SEC = 120.0
# A once-grant followed quickly by a same-app request with a different
# fingerprint surfaces a "target changed" flag on the approval card.
_GRANT_CHANGE_WINDOW_SEC = 300.0
_REASON_MAX_LEN = 500


def approval_fingerprint(*, operation: str, trust_key: str) -> str:
    """Stable execution fingerprint binding one approval to one operation.

    Only stable identity participates: the app trust key plus the requested
    operation. Volatile presentation (window title, reason text) is excluded
    so legitimate re-prompts do not flap.
    """
    digest = hashlib.sha1(
        f"{operation.strip()}\0{trust_key.strip()}".encode("utf-8"),
        usedforsecurity=False,
    )
    return digest.hexdigest()[:16]


def _deny_key(*, trust_key: str, fingerprint: str) -> str:
    return f"{trust_key}\0{fingerprint}"


class TrustedAppRecord(TypedDict):
    trust_key: str
    display_name: str
    app_id: str
    scope: str


@dataclass(slots=True)
class _PendingApproval:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    result: ForegroundPermissionResult | None = None
    # Request metadata carried for observability and grant binding. Populated
    # at creation; never trusted for authorization by itself.
    created_at: float = 0.0
    reason: str = ""
    operation: str = ""
    app_name: str = ""
    window_title: str = ""
    app_id: str = ""
    fingerprint: str = ""
    test_only: bool = False
    # Settlement provenance: "user" (explicit resolve), "recovery" (dev reset),
    # "" (undecided/timeout). Only "user" refusals become durable denials.
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
    # Settled-without-decision markers: timeout or cap eviction. Bounded with
    # TTL so resolve-after-timeout reports "expired" instead of "missing".
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
            # Fail closed: drop the oldest undecided request instead of
            # growing without bound.
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


class DesktopControlGate:
    """Server-side gate implementing ForegroundPermissionCallback for desktop tools."""

    _live_gates: weakref.WeakSet[DesktopControlGate] = weakref.WeakSet()

    def __init__(
        self,
        *,
        workspace_root: str | None,
        auto_grant: bool = False,
        default_timeout_seconds: float = _DEFAULT_TIMEOUT_SEC,
        register_live: bool = True,
        preapproved_trust_keys: Collection[str] | None = None,
        unattended_fail_fast: bool = False,
    ) -> None:
        self._workspace_root = Path(workspace_root) if workspace_root else None
        self._auto_grant = auto_grant
        self._default_timeout = default_timeout_seconds
        self._unattended_fail_fast = unattended_fail_fast
        self._session_approved_keys: set[str] = set()
        self._always_approved_keys: set[str] = set()
        self._run_scoped_keys: set[str] = set()
        # Session-final denials (explicit user refusals): same trust key plus
        # same execution fingerprint is denied without re-prompting until the
        # session state resets. Timeouts never land here.
        self._denied_session_keys: set[str] = set()
        # Operator-configured denials persisted in denied_apps.json. These
        # survive runtime resets; session denials do not.
        self._denied_persistent_keys: set[str] = set()
        # Last once-grant per trust key for drift surfacing (A): a same-app
        # request with a different fingerprint inside the window flags the
        # approval card instead of silently proceeding.
        self._last_grants: dict[str, tuple[str, float]] = {}
        self._trusted_app_records: dict[str, TrustedAppRecord] = {}
        self._load_persisted_apps()
        self._load_denied_apps()
        if preapproved_trust_keys:
            seeded = {str(key).strip() for key in preapproved_trust_keys if str(key).strip()}
            self._run_scoped_keys.update(seeded)
            self._session_approved_keys.update(seeded)
        if register_live:
            DesktopControlGate._live_gates.add(self)

    def reset_runtime_approval_state(self) -> None:
        """Clear in-memory approval caches and reload persisted always-approved apps.

        Session-final denials reset with the session; operator-configured
        persistent denials survive and reload from disk.
        """
        self._session_approved_keys.clear()
        self._always_approved_keys.clear()
        self._denied_session_keys.clear()
        self._last_grants.clear()
        self._trusted_app_records.clear()
        self._load_persisted_apps()
        self._load_denied_apps()

    @classmethod
    def reset_all_runtime_approval_state(cls) -> None:
        DesktopApprovalRegistry.clear_all()
        for gate in list(cls._live_gates):
            gate.reset_runtime_approval_state()
        try:
            from app.services.agent.gateway import get_agent_gateway

            cleared = get_agent_gateway().reset_all_desktop_session_permission_caches()
            if cleared:
                logger.info(
                    "Reset desktop session permission caches on %s active agent(s)",
                    cleared,
                )
        except Exception as exc:
            logger.warning(
                "Failed to reset active desktop session permission caches: %s",
                exc,
            )

    def _approval_path(self) -> Path | None:
        if self._workspace_root is None:
            return None
        return self._workspace_root / _APPROVAL_DIR / _APPROVAL_FILE

    def _deny_path(self) -> Path | None:
        if self._workspace_root is None:
            return None
        return self._workspace_root / _APPROVAL_DIR / _DENY_FILE

    def _load_denied_apps(self) -> None:
        """Load operator-configured persistent denials (workspace scope).

        Format: {"denied": ["<trust_key>", ...]}. Unknown shapes are ignored
        so older approved_apps.json files keep loading untouched.
        """
        self._denied_persistent_keys.clear()
        path = self._deny_path()
        if path is None or not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load desktop deny file: %s", exc)
            return
        denied = raw.get("denied", []) if isinstance(raw, dict) else []
        if not isinstance(denied, list):
            return
        for key in denied:
            if isinstance(key, str) and key.strip():
                self._denied_persistent_keys.add(key.strip())

    def _is_denied(self, *, trust_key: str, fingerprint: str) -> bool:
        if trust_key and trust_key in self._denied_persistent_keys:
            return True
        if trust_key and _deny_key(trust_key=trust_key, fingerprint=fingerprint) in self._denied_session_keys:
            return True
        return False

    @staticmethod
    def _parse_trusted_entry(key: str, entry: object) -> TrustedAppRecord | None:
        if not isinstance(entry, dict):
            return None
        scope = entry.get("scope")
        if scope != ForegroundPermissionScope.always.value:
            return None
        display_name = str(entry.get("display_name") or key).strip()
        app_id = str(entry.get("app_id") or "").strip()
        trust_key = resolve_trust_key(app_name=display_name, app_id=app_id) or key.strip()
        if not trust_key:
            return None
        return {
            "trust_key": trust_key,
            "display_name": display_name or key,
            "app_id": app_id,
            "scope": ForegroundPermissionScope.always.value,
        }

    def _load_persisted_apps(self) -> None:
        path = self._approval_path()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            apps = data.get("apps", {})
            if not isinstance(apps, dict):
                return
            for key, entry in apps.items():
                if not isinstance(key, str):
                    continue
                record = self._parse_trusted_entry(key, entry)
                if record is None:
                    continue
                trust_key = record["trust_key"]
                self._always_approved_keys.add(trust_key)
                self._trusted_app_records[trust_key] = record
        except Exception as exc:
            logger.warning("Failed to load desktop approval file: %s", exc)

    def _is_app_preapproved(self, app_name: str, app_id: str = "") -> bool:
        for stored_key in self._always_approved_keys | self._session_approved_keys:
            if trust_key_matches(stored_key, app_name=app_name, app_id=app_id):
                return True
        return False

    def list_trusted_apps(self) -> list[TrustedAppRecord]:
        return sorted(
            self._trusted_app_records.values(),
            key=lambda item: item["display_name"].lower(),
        )

    def revoke_trusted_app(self, trust_key: str) -> bool:
        normalized = trust_key.strip()
        if not normalized or normalized not in self._trusted_app_records:
            return False

        self._trusted_app_records.pop(normalized, None)
        self._always_approved_keys.discard(normalized)
        self._session_approved_keys.discard(normalized)

        path = self._approval_path()
        if path is None:
            return True

        remaining = {
            record["trust_key"]: {
                "scope": ForegroundPermissionScope.always.value,
                "display_name": record["display_name"],
                "app_id": record["app_id"],
            }
            for record in self._trusted_app_records.values()
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"apps": remaining}, indent=2), encoding="utf-8")
        return True

    def _persist_app(self, app_name: str, app_id: str = "") -> None:
        path = self._approval_path()
        if path is None or not app_name.strip():
            return

        trust_key = resolve_trust_key(app_name=app_name, app_id=app_id)
        if not trust_key:
            return

        existing: dict[str, object] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("apps"), dict):
                    existing = dict(raw["apps"])
            except Exception:
                existing = {}

        existing[trust_key] = {
            "scope": ForegroundPermissionScope.always.value,
            "display_name": app_name.strip(),
            "app_id": app_id.strip(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"apps": existing}, indent=2), encoding="utf-8")

        record: TrustedAppRecord = {
            "trust_key": trust_key,
            "display_name": app_name.strip(),
            "app_id": app_id.strip(),
            "scope": ForegroundPermissionScope.always.value,
        }
        self._always_approved_keys.add(trust_key)
        self._trusted_app_records[trust_key] = record

    def _grant_changed(self, *, trust_key: str, fingerprint: str) -> bool:
        """Whether a same-app request drifts from the last once-grant.

        The approval card surfaces this flag so the user re-confirms a
        changed target instead of reflex-approving a stale context.
        """
        if not trust_key:
            return False
        last = self._last_grants.get(trust_key)
        if last is None:
            return False
        last_fingerprint, granted_at = last
        return last_fingerprint != fingerprint and (time.monotonic() - granted_at) <= _GRANT_CHANGE_WINDOW_SEC

    async def __call__(
        self,
        *,
        reason: str,
        operation: str,
        estimated_duration_seconds: float,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SEC,
        app_name: str = "",
        window_title: str = "",
        app_id: str = "",
        require_app_approval: bool = True,
    ) -> ForegroundPermissionResult:
        del estimated_duration_seconds

        trust_key = resolve_trust_key(app_name=app_name, app_id=app_id) or ""
        fingerprint = approval_fingerprint(operation=operation, trust_key=trust_key)

        if self._auto_grant:
            # Cloud-sandbox posture (no human watching): grant with an audit
            # trail. Call sites enable auto_grant for sandbox non-local mode
            # only; local runs must never reach here.
            logger.warning(
                "Desktop approval auto-granted (sandbox, app=%r op=%r fp=%s)",
                app_name,
                operation,
                fingerprint,
            )
            if trust_key:
                self._session_approved_keys.add(trust_key)
            DesktopApprovalRegistry.record_decision(
                request_id="",
                trust_key=trust_key,
                fingerprint=fingerprint,
                operation=operation,
                decision="auto_granted",
                scope=ForegroundPermissionScope.always.value,
            )
            return ForegroundPermissionResult(
                granted=True,
                scope=ForegroundPermissionScope.always,
            )

        if require_app_approval and trust_key and self._is_denied(trust_key=trust_key, fingerprint=fingerprint):
            # Deny-first: persistent operator denials and session-final user
            # refusals win over every allow cache below.
            logger.info(
                "Desktop approval denied by rule (app=%r op=%r fp=%s)",
                app_name,
                operation,
                fingerprint,
            )
            DesktopApprovalRegistry.record_decision(
                request_id="",
                trust_key=trust_key,
                fingerprint=fingerprint,
                operation=operation,
                decision="denied_by_rule",
            )
            return ForegroundPermissionResult(granted=False)

        if require_app_approval and self._is_app_preapproved(app_name, app_id):
            return ForegroundPermissionResult(
                granted=True,
                scope=ForegroundPermissionScope.once,
            )

        if require_app_approval and self._run_scoped_keys:
            trust_key = resolve_trust_key(app_name=app_name, app_id=app_id)
            if trust_key and trust_key in self._run_scoped_keys:
                return ForegroundPermissionResult(
                    granted=True,
                    scope=ForegroundPermissionScope.once,
                )

        if self._unattended_fail_fast:
            # Unattended runs (e.g. cron) have no human to answer the approval
            # card: deny immediately instead of burning the full approval timeout.
            logger.warning(
                "Desktop approval fast-denied (unattended, app=%r op=%r)",
                app_name,
                operation,
            )
            return ForegroundPermissionResult(granted=False)

        sink = get_tool_progress_sink()
        if sink is None:
            return ForegroundPermissionResult(granted=False)

        changed = self._grant_changed(trust_key=trust_key, fingerprint=fingerprint)
        request_id, pending = DesktopApprovalRegistry.create(
            reason=reason,
            operation=operation,
            app_name=app_name,
            window_title=window_title,
            app_id=app_id,
            fingerprint=fingerprint,
        )
        await sink.emit(
            {
                "type": AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST,
                "data": {
                    "request_id": request_id,
                    "reason": reason,
                    "operation": operation,
                    "app_name": app_name,
                    "window_title": window_title,
                    "app_id": app_id,
                    "require_app_approval": require_app_approval,
                    "timeout_seconds": timeout_seconds,
                    "fingerprint": fingerprint,
                    "changed_since_last_grant": changed,
                },
            }
        )

        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout_seconds)
        except TimeoutError:
            if pending.result is not None:
                # A user decision landed between the deadline check and this
                # branch: honor the answer instead of manufacturing a timeout.
                return self._settle_user_decision(
                    pending=pending,
                    request_id=request_id,
                    trust_key=trust_key,
                    fingerprint=fingerprint,
                    operation=operation,
                    app_name=app_name,
                    app_id=app_id,
                    require_app_approval=require_app_approval,
                )
            DesktopApprovalRegistry._settle_timeout(request_id)
            DesktopApprovalRegistry.record_decision(
                request_id=request_id,
                trust_key=trust_key,
                fingerprint=fingerprint,
                operation=operation,
                decision="timeout",
            )
            await self._emit_withdraw(sink, request_id=request_id)
            return ForegroundPermissionResult(granted=False)

        result = pending.result or ForegroundPermissionResult(granted=False)
        return self._settle_user_decision(
            pending=pending,
            request_id=request_id,
            trust_key=trust_key,
            fingerprint=fingerprint,
            operation=operation,
            app_name=app_name,
            app_id=app_id,
            require_app_approval=require_app_approval,
            result=result,
        )

    def _settle_user_decision(
        self,
        *,
        pending: _PendingApproval,
        request_id: str,
        trust_key: str,
        fingerprint: str,
        operation: str,
        app_name: str,
        app_id: str,
        require_app_approval: bool,
        result: ForegroundPermissionResult | None = None,
    ) -> ForegroundPermissionResult:
        """Apply one explicit user decision (grant persists, denial endures).

        Recovery denials (E2E/dev reset) and timeouts never become durable:
        only a human refusal finalizes the key for the session.
        """
        decided = result if result is not None else pending.result
        if decided is None:
            return ForegroundPermissionResult(granted=False)
        if decided.granted:
            if trust_key:
                self._last_grants[trust_key] = (fingerprint, time.monotonic())
            if app_name.strip() and require_app_approval and trust_key:
                if decided.scope == ForegroundPermissionScope.session:
                    self._session_approved_keys.add(trust_key)
                elif decided.scope == ForegroundPermissionScope.always:
                    self._persist_app(app_name, app_id)
            DesktopApprovalRegistry.record_decision(
                request_id=request_id,
                trust_key=trust_key,
                fingerprint=fingerprint,
                operation=operation,
                decision="granted",
                scope=decided.scope.value,
            )
            return decided
        if pending.decided_by == "user" and trust_key:
            self._denied_session_keys.add(_deny_key(trust_key=trust_key, fingerprint=fingerprint))
            DesktopApprovalRegistry.record_decision(
                request_id=request_id,
                trust_key=trust_key,
                fingerprint=fingerprint,
                operation=operation,
                decision="denied",
                reason=pending.deny_reason,
            )
        return decided

    @staticmethod
    async def _emit_withdraw(sink: object, *, request_id: str) -> None:
        """Best-effort withdraw card so stale approval banners clear.

        Reuses the approval-request event with a withdrawn flag: old clients
        ignore the unknown field, new clients clear the matching banner.
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


def resolve_desktop_control_approval(
    request_id: str,
    *,
    granted: bool,
    scope: str = "once",
    reason: str = "",
) -> bool:
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


def _trust_store_workspace_roots(*, fallback_root: str | None) -> list[Path]:
    """Collect chat/agent workspace roots that may hold approved_apps.json."""
    roots: list[Path] = []
    seen: set[str] = set()

    def _add(candidate: Path | None) -> None:
        if candidate is None:
            return
        resolved = str(candidate.expanduser().resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(Path(resolved))

    for gate in DesktopControlGate._live_gates:
        _add(gate._workspace_root)

    try:
        from app.config.settings import get_settings

        harness_dir = Path(get_settings().database.harness_dir)
        if harness_dir.is_dir():
            # approved_apps.json only ever lives at
            # {workspace_root}/.agent/desktop_control/approved_apps.json, and
            # harness workspaces use a two-level layout (e.g.
            # harness/workspaces/chat_*/...). Probe that bounded layout with
            # os.scandir instead of a full recursive rglob over the whole
            # harness dir, which can contain tens of thousands of files.
            def _collect(root: str) -> None:
                try:
                    with os.scandir(root) as entries:
                        for entry in entries:
                            if not entry.is_dir(follow_symlinks=False):
                                continue
                            agent_dir = os.path.join(entry.path, _APPROVAL_DIR)
                            if os.path.isdir(agent_dir) and os.path.isfile(os.path.join(agent_dir, _APPROVAL_FILE)):
                                _add(Path(entry.path))
                except OSError:
                    return

            try:
                collections = [entry.path for entry in os.scandir(harness_dir) if entry.is_dir(follow_symlinks=False)]
            except OSError:
                collections = []
            for collection in collections:
                agent_dir = os.path.join(collection, _APPROVAL_DIR)
                if os.path.isdir(agent_dir) and os.path.isfile(os.path.join(agent_dir, _APPROVAL_FILE)):
                    _add(Path(collection))
                else:
                    _collect(collection)
    except Exception as exc:
        logger.warning("Failed to scan harness desktop trust stores: %s", exc)

    if fallback_root:
        _add(Path(fallback_root))

    return roots


def _disk_trusted_apps_for_workspace(workspace_root: str) -> list[TrustedAppRecord]:
    gate = DesktopControlGate(
        workspace_root=workspace_root,
        auto_grant=False,
        register_live=False,
    )
    return gate.list_trusted_apps()


def list_trusted_desktop_apps(*, workspace_root: str | None) -> list[TrustedAppRecord]:
    merged: dict[str, TrustedAppRecord] = {}
    for gate in list(DesktopControlGate._live_gates):
        for record in gate.list_trusted_apps():
            merged[record["trust_key"]] = record
    for root in _trust_store_workspace_roots(fallback_root=workspace_root):
        for record in _disk_trusted_apps_for_workspace(str(root)):
            merged.setdefault(record["trust_key"], record)
    return sorted(merged.values(), key=lambda item: item["display_name"].lower())


def revoke_trusted_desktop_app(*, workspace_root: str | None, trust_key: str) -> bool:
    for gate in list(DesktopControlGate._live_gates):
        if gate.revoke_trusted_app(trust_key):
            return True
    for root in _trust_store_workspace_roots(fallback_root=workspace_root):
        disk_gate = DesktopControlGate(
            workspace_root=str(root),
            auto_grant=False,
            register_live=False,
        )
        if disk_gate.revoke_trusted_app(trust_key):
            return True
    return False
