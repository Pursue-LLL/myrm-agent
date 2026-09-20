"""Desktop control gate — per-app approval and foreground permission.

[INPUT]
- myrm_agent_harness.toolkits.computer_use.types::ForegroundPermissionResult, ForegroundPermissionScope
- myrm_agent_harness.toolkits.computer_use.app_identity::resolve_trust_key, trust_key_matches
- myrm_agent_harness.core.events.types::AgentEventType
- myrm_agent_harness.utils.runtime.progress_sink::get_tool_progress_sink
- app.ai_agents.desktop_control.registry::DesktopApprovalRegistry (POS: approval ledger), approval_fingerprint, deny_key_for, grant_changed_since, emit_withdraw_card
- app.ai_agents.desktop_control.trust_store::TrustedAppRecord (POS: trust persistence), load_denied_keys, _APPROVAL_DIR, _APPROVAL_FILE

[OUTPUT]
- DesktopControlGate: async callback for foreground permission requests
  with deny-first evaluation, fingerprint-bound grants, and session-final refusals

[POS]
Server-layer gate that bridges harness ForegroundPermissionCallback with
frontend approval UI via SSE events. Evaluates deny rules before allow
caches and issues one prompt per undecided request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import weakref
from collections.abc import Collection
from pathlib import Path

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

from app.ai_agents.desktop_control.registry import (
    DesktopApprovalRegistry,
    _PendingApproval,
    approval_fingerprint,
    deny_key_for,
    emit_withdraw_card,
    grant_changed_since,
)
from app.ai_agents.desktop_control.trust_store import (
    _APPROVAL_DIR,
    _APPROVAL_FILE,
    TrustedAppRecord,
    load_denied_keys,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SEC = 60.0
_raw_timeout = os.getenv("MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC", "60").strip()
try:
    _parsed_timeout = float(_raw_timeout)
except ValueError:
    _parsed_timeout = _DEFAULT_TIMEOUT_SEC
_DEFAULT_TIMEOUT_SEC = max(5.0, _parsed_timeout)


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
        # Last once-grant per trust key for drift surfacing: a same-app
        # request with a different fingerprint inside the window flags the
        # approval card.
        self._last_grants: dict[str, tuple[str, float]] = {}
        self._trusted_app_records: dict[str, TrustedAppRecord] = {}
        self._load_persisted_apps()
        root = str(self._workspace_root) if self._workspace_root is not None else None
        self._denied_persistent_keys = load_denied_keys(workspace_root=root)
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
        root = str(self._workspace_root) if self._workspace_root is not None else None
        self._denied_persistent_keys = load_denied_keys(workspace_root=root)

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

    def _is_denied(self, *, trust_key: str, fingerprint: str) -> bool:
        if trust_key and trust_key in self._denied_persistent_keys:
            return True
        if trust_key and deny_key_for(trust_key=trust_key, fingerprint=fingerprint) in self._denied_session_keys:
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

        changed = grant_changed_since(
            self._last_grants.get(trust_key),
            fingerprint=fingerprint,
            now=time.monotonic(),
        )
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
                # branch: the late answer wins.
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
            await emit_withdraw_card(sink, request_id=request_id)
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
            self._denied_session_keys.add(deny_key_for(trust_key=trust_key, fingerprint=fingerprint))
            DesktopApprovalRegistry.record_decision(
                request_id=request_id,
                trust_key=trust_key,
                fingerprint=fingerprint,
                operation=operation,
                decision="denied",
                reason=pending.deny_reason,
            )
        return decided
