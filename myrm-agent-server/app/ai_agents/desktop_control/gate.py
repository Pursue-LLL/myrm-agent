"""Desktop control gate — per-app approval and foreground permission.

[INPUT]
- myrm_agent_harness.toolkits.computer_use.types::ForegroundPermissionResult, ForegroundPermissionScope
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
import uuid
import weakref
from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.core.events.types import AgentEventType
from myrm_agent_harness.toolkits.computer_use.types import (
    ForegroundPermissionResult,
    ForegroundPermissionScope,
)
from myrm_agent_harness.utils.runtime.progress_sink import get_tool_progress_sink

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SEC = 30.0
_APPROVAL_DIR = ".agent/desktop_control"
_APPROVAL_FILE = "approved_apps.json"


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
    ) -> None:
        self._workspace_root = Path(workspace_root) if workspace_root else None
        self._auto_grant = auto_grant
        self._default_timeout = default_timeout_seconds
        self._session_approved_apps: set[str] = set()
        self._always_approved_apps: set[str] = set()
        self._load_persisted_apps()
        DesktopControlGate._live_gates.add(self)

    def reset_runtime_approval_state(self) -> None:
        """Clear in-memory approval caches and reload persisted always-approved apps."""
        self._session_approved_apps.clear()
        self._always_approved_apps.clear()
        self._load_persisted_apps()

    @classmethod
    def reset_all_runtime_approval_state(cls) -> None:
        for gate in list(cls._live_gates):
            gate.reset_runtime_approval_state()

    def _approval_path(self) -> Path | None:
        if self._workspace_root is None:
            return None
        return self._workspace_root / _APPROVAL_DIR / _APPROVAL_FILE

    def _load_persisted_apps(self) -> None:
        path = self._approval_path()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            apps = data.get("apps", {})
            if isinstance(apps, dict):
                self._always_approved_apps = {
                    name.strip().lower()
                    for name, entry in apps.items()
                    if isinstance(name, str)
                    and isinstance(entry, dict)
                    and entry.get("scope") == ForegroundPermissionScope.always.value
                }
        except Exception as exc:
            logger.warning("Failed to load desktop approval file: %s", exc)

    def _is_app_preapproved(self, app_name: str) -> bool:
        key = app_name.strip().lower()
        if not key:
            return False
        return key in self._always_approved_apps or key in self._session_approved_apps

    def _persist_app(self, app_name: str) -> None:
        path = self._approval_path()
        if path is None or not app_name.strip():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, object] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("apps"), dict):
                    existing = dict(raw["apps"])
            except Exception:
                existing = {}
        existing[app_name] = {"scope": ForegroundPermissionScope.always.value}
        path.write_text(json.dumps({"apps": existing}, indent=2), encoding="utf-8")
        self._always_approved_apps.add(app_name.strip().lower())

    async def __call__(
        self,
        *,
        reason: str,
        operation: str,
        estimated_duration_seconds: float,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SEC,
        app_name: str = "",
        window_title: str = "",
        require_app_approval: bool = True,
    ) -> ForegroundPermissionResult:
        del estimated_duration_seconds

        if self._auto_grant:
            if app_name.strip():
                self._session_approved_apps.add(app_name.strip().lower())
            return ForegroundPermissionResult(
                granted=True,
                scope=ForegroundPermissionScope.always,
            )

        if require_app_approval and self._is_app_preapproved(app_name):
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
            if result.scope == ForegroundPermissionScope.session:
                self._session_approved_apps.add(app_name.strip().lower())
            elif result.scope == ForegroundPermissionScope.always:
                self._persist_app(app_name)
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
