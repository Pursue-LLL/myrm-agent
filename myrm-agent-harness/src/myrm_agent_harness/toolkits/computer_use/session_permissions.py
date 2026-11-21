"""Permission gates of the computer session: foreground control and per-application approval.

[INPUT]
- backends.protocols::ComputerBackend (POS: platform I/O the session owns; read for the foreground application)
- perception.ax_dispatch::inspect_backend, run_ax_call (POS: foreground application lookup, off the event loop on macOS)
- types::ActionResult, ComputerUseConfig, ExecutionMode, ForegroundPermissionCallback, ForegroundPermissionScope (POS: shared types)

[OUTPUT]
- ComputerPermissionMixin: check_foreground_permission, check_app_approval, clear_operation_foreground_waiver, reset_runtime_permission_cache

[POS]
The user-permission half of ComputerSession: what a foreground-stealing or per-application operation must be granted
before it runs, and the grants kept for the session. ComputerSession owns the state and the callback; this mixin
only reads and updates them.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.computer_use.backends.protocols import ComputerBackend
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ComputerUseConfig,
    ExecutionMode,
    ForegroundPermissionCallback,
    ForegroundPermissionScope,
)

logger = logging.getLogger(__name__)


class ComputerPermissionMixin:
    """Foreground and per-application permission gates of a computer session."""

    _backend: ComputerBackend
    _config: ComputerUseConfig
    _permission_callback: ForegroundPermissionCallback | None
    _session_permission_granted: bool
    _always_permission_granted: bool
    _operation_foreground_waived: bool

    def reset_runtime_permission_cache(self) -> None:
        """Clear in-memory foreground/app approval shortcuts (E2E/dev recovery)."""
        self._session_permission_granted = False
        self._always_permission_granted = False
        self._operation_foreground_waived = False

    async def check_foreground_permission(
        self,
        *,
        reason: str,
        operation: str,
        estimated_duration_seconds: float = 5.0,
        app_name: str = "",
        window_title: str = "",
        app_id: str = "",
    ) -> ActionResult | None:
        """Gate foreground-stealing operations behind user permission.

        Returns None if permission is granted (proceed with execution).
        Returns an ActionResult with error if permission is denied or unavailable.
        """
        mode = self._config.execution_mode

        if mode == ExecutionMode.foreground:
            return None

        if self._always_permission_granted or self._session_permission_granted:
            return None

        if self._operation_foreground_waived:
            return None

        if self._permission_callback is None:
            if mode == ExecutionMode.background_strict:
                return ActionResult(
                    success=False,
                    error="Foreground operation blocked: execution_mode is background_strict "
                    "and no permission callback is configured.",
                )
            return None

        result = await self._permission_callback(
            reason=reason,
            operation=operation,
            estimated_duration_seconds=estimated_duration_seconds,
            app_name=app_name,
            window_title=window_title,
            app_id=app_id,
            require_app_approval=False,
        )

        if not result.granted:
            return ActionResult(
                success=False,
                error=f"Foreground permission denied by user. Reason: {reason}",
            )

        if result.scope == ForegroundPermissionScope.session:
            self._session_permission_granted = True
        elif result.scope == ForegroundPermissionScope.always:
            self._always_permission_granted = True

        logger.info("Foreground permission granted (scope=%s): %s", result.scope.value, reason)
        return None

    async def check_app_approval(
        self,
        *,
        app_name: str,
        window_title: str,
        operation: str,
        estimated_duration_seconds: float = 5.0,
        app_id: str = "",
    ) -> ActionResult | None:
        """Gate first-time per-app desktop interaction behind user approval."""
        resolved_app = app_name.strip()
        resolved_title = window_title.strip()
        resolved_app_id = app_id.strip()

        if not resolved_app:
            from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import inspect_backend, run_ax_call

            fg_info = await run_ax_call(self._backend, inspect_backend, self._backend)
            resolved_app = str(fg_info.get("app_name", "") or "").strip()
            resolved_app_id = str(fg_info.get("app_id", "") or "").strip()
            if not resolved_title:
                resolved_title = str(fg_info.get("window_title", "") or "").strip()

        if not resolved_app:
            if self._permission_callback is not None or self._config.execution_mode == ExecutionMode.background_strict:
                return ActionResult(
                    success=False,
                    error=(
                        "Desktop control blocked: could not identify the foreground application "
                        "for approval. Call desktop_snapshot_tool first or grant Accessibility access."
                    ),
                )
            return None

        if self._permission_callback is None:
            if self._config.execution_mode == ExecutionMode.background_strict:
                return ActionResult(
                    success=False,
                    error="Desktop app control blocked: no permission callback is configured.",
                )
            return None

        result = await self._permission_callback(
            reason=f"Agent wants to control application '{resolved_app}'",
            operation=operation,
            estimated_duration_seconds=estimated_duration_seconds,
            app_name=resolved_app,
            window_title=resolved_title,
            app_id=resolved_app_id,
            require_app_approval=True,
        )

        if not result.granted:
            return ActionResult(
                success=False,
                error=f"Desktop control denied for application '{resolved_app}'.",
            )

        if result.scope == ForegroundPermissionScope.session:
            self._session_permission_granted = True
        elif result.scope == ForegroundPermissionScope.always:
            self._always_permission_granted = True

        self._operation_foreground_waived = True
        return None

    def clear_operation_foreground_waiver(self) -> None:
        """Clear one-shot foreground waiver after the current desktop tool call finishes."""
        self._operation_foreground_waived = False
