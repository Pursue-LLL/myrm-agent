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
import json
import logging
import os
import uuid
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from myrm_agent_harness.core.events.types import AgentEventType
from myrm_agent_harness.toolkits.computer_use.app_identity import resolve_trust_key, trust_key_matches
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


class TrustedAppRecord(TypedDict):
    trust_key: str
    display_name: str
    app_id: str
    scope: str


@dataclass(slots=True)
class _PendingApproval:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    result: ForegroundPermissionResult | None = None


class DesktopApprovalRegistry:
    """In-memory pending desktop approval requests keyed by request_id."""

    _pending: dict[str, _PendingApproval] = {}

    @classmethod
    def create(cls) -> tuple[str, _PendingApproval]:
        request_id = uuid.uuid4().hex
        pending = _PendingApproval()
        cls._pending[request_id] = pending
        return request_id, pending

    @classmethod
    def resolve(
        cls,
        request_id: str,
        *,
        granted: bool,
        scope: ForegroundPermissionScope,
    ) -> bool:
        pending = cls._pending.pop(request_id, None)
        if pending is None:
            return False
        pending.result = ForegroundPermissionResult(granted=granted, scope=scope)
        pending.event.set()
        return True

    @classmethod
    def pending_snapshot(cls) -> list[str]:
        return list(cls._pending.keys())


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
    ) -> None:
        self._workspace_root = Path(workspace_root) if workspace_root else None
        self._auto_grant = auto_grant
        self._default_timeout = default_timeout_seconds
        self._session_approved_keys: set[str] = set()
        self._always_approved_keys: set[str] = set()
        self._trusted_app_records: dict[str, TrustedAppRecord] = {}
        self._load_persisted_apps()
        if register_live:
            DesktopControlGate._live_gates.add(self)

    def reset_runtime_approval_state(self) -> None:
        """Clear in-memory approval caches and reload persisted always-approved apps."""
        self._session_approved_keys.clear()
        self._always_approved_keys.clear()
        self._trusted_app_records.clear()
        self._load_persisted_apps()

    @classmethod
    def reset_all_runtime_approval_state(cls) -> None:
        for gate in list(cls._live_gates):
            gate.reset_runtime_approval_state()

    def _approval_path(self) -> Path | None:
        if self._workspace_root is None:
            return None
        return self._workspace_root / _APPROVAL_DIR / _APPROVAL_FILE

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

        if self._auto_grant:
            trust_key = resolve_trust_key(app_name=app_name, app_id=app_id)
            if trust_key:
                self._session_approved_keys.add(trust_key)
            return ForegroundPermissionResult(
                granted=True,
                scope=ForegroundPermissionScope.always,
            )

        if require_app_approval and self._is_app_preapproved(app_name, app_id):
            return ForegroundPermissionResult(
                granted=True,
                scope=ForegroundPermissionScope.once,
            )

        sink = get_tool_progress_sink()
        if sink is None:
            return ForegroundPermissionResult(granted=False)

        request_id, pending = DesktopApprovalRegistry.create()
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
                },
            }
        )

        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout_seconds)
        except TimeoutError:
            DesktopApprovalRegistry.resolve(
                request_id,
                granted=False,
                scope=ForegroundPermissionScope.once,
            )
            return ForegroundPermissionResult(granted=False)

        result = pending.result or ForegroundPermissionResult(granted=False)
        if result.granted and app_name.strip() and require_app_approval:
            trust_key = resolve_trust_key(app_name=app_name, app_id=app_id)
            if trust_key:
                if result.scope == ForegroundPermissionScope.session:
                    self._session_approved_keys.add(trust_key)
                elif result.scope == ForegroundPermissionScope.always:
                    self._persist_app(app_name, app_id)
        return result


def resolve_desktop_control_approval(
    request_id: str,
    *,
    granted: bool,
    scope: str = "once",
) -> bool:
    try:
        scope_enum = ForegroundPermissionScope(scope)
    except ValueError:
        scope_enum = ForegroundPermissionScope.once
    return DesktopApprovalRegistry.resolve(request_id, granted=granted, scope=scope_enum)


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
            for approval_file in harness_dir.rglob(_APPROVAL_FILE):
                _add(approval_file.parent.parent.parent)
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
