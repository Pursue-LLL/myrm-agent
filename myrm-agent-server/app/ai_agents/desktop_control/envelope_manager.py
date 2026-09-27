"""Desktop intent envelope manager and lease tracker.

[INPUT]
- myrm_agent_harness.toolkits.computer_use.envelope::IntentEnvelopeSpec, WindowHierarchyContext, EnvelopeCheckResult, check_envelope_action
- myrm_agent_harness.core.events.types::AgentEventType
- myrm_agent_harness.utils.runtime.progress_sink::get_tool_progress_sink

[OUTPUT]
- DesktopEnvelopeManager: task-scoped envelope registration, verification, and lease extension

[POS]
Server-layer manager that tracks the active execution envelope, consumes step quota,
inherits modal window trusts, and dispatches progress updates to the frontend.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from myrm_agent_harness.core.events.types import AgentEventType
from myrm_agent_harness.toolkits.computer_use.envelope import (
    IntentEnvelopeSpec,
    WindowHierarchyContext,
    check_envelope_action,
)
from myrm_agent_harness.utils.runtime.progress_sink import get_tool_progress_sink

logger = logging.getLogger(__name__)

# Hard limits for safety guardrails
_MAX_LEASE_HARD_LIMIT = 100
_DEFAULT_LEASE_EXTEND_STEP = 10
_MAX_ENVELOPES_CAPACITY = 200


class DesktopEnvelopeManager:
    """Manages active task intent envelopes and non-interruptive action quotas."""

    def __init__(self) -> None:
        self._active_envelope: IntentEnvelopeSpec | None = None
        self._envelopes_by_task: dict[str, IntentEnvelopeSpec] = {}
        self._last_active_by_task: dict[str, float] = {}

    @property
    def active_envelope(self) -> IntentEnvelopeSpec | None:
        """Return the currently active intent envelope, if any."""
        return self._active_envelope

    def register_envelope(self, spec: IntentEnvelopeSpec) -> None:
        """Register and activate an intent envelope for a task."""
        clamped_max = min(max(1, spec.max_actions), _MAX_LEASE_HARD_LIMIT)
        spec.max_actions = clamped_max
        if len(self._envelopes_by_task) >= _MAX_ENVELOPES_CAPACITY:
            candidates = [k for k in self._last_active_by_task if k != spec.task_id]
            if candidates:
                oldest_task = min(candidates, key=lambda k: self._last_active_by_task.get(k, 0.0))
                self._envelopes_by_task.pop(oldest_task, None)
                self._last_active_by_task.pop(oldest_task, None)
        self._envelopes_by_task[spec.task_id] = spec
        self._last_active_by_task[spec.task_id] = time.monotonic()
        self._active_envelope = spec
        logger.info(
            "Registered intent envelope for task %s (apps=%s, budget=%d, idle_timeout=%.1fs)",
            spec.task_id,
            spec.allowed_app_names or spec.allowed_app_ids,
            spec.max_actions,
            spec.idle_timeout_seconds,
        )

    def get_envelope(self, task_id: str | None = None) -> IntentEnvelopeSpec | None:
        """Get envelope by task_id or current active envelope."""
        if task_id:
            return self._envelopes_by_task.get(task_id)
        return self._active_envelope

    def clear_envelope(self, task_id: str | None = None) -> None:
        """Clear active envelope or specified task envelope."""
        if task_id:
            self._envelopes_by_task.pop(task_id, None)
            self._last_active_by_task.pop(task_id, None)
            if self._active_envelope and self._active_envelope.task_id == task_id:
                self._active_envelope = None
        else:
            self._active_envelope = None
            self._envelopes_by_task.clear()
            self._last_active_by_task.clear()

    def extend_lease(
        self,
        additional_steps: int = _DEFAULT_LEASE_EXTEND_STEP,
        task_id: str | None = None,
    ) -> int:
        """Extend the step budget of the active envelope in-place.

        Returns:
            The new total max_actions limit.
        """
        envelope = self.get_envelope(task_id)
        if not envelope:
            return 0

        new_max = min(envelope.max_actions + max(1, additional_steps), _MAX_LEASE_HARD_LIMIT)
        envelope.max_actions = new_max
        self._last_active_by_task[envelope.task_id] = time.monotonic()
        logger.info(
            "Extended lease for envelope %s: new limit=%d (used=%d)",
            envelope.task_id,
            new_max,
            envelope.used_actions,
        )
        return new_max

    def evaluate_and_consume(
        self,
        *,
        app_name: str,
        app_id: str,
        window_title: str = "",
        text_to_type: str = "",
        parent_app_id: str | None = None,
        is_system_dialog: bool = False,
        task_id: str | None = None,
    ) -> tuple[bool, Literal["ok", "no_envelope", "out_of_boundary", "budget_exhausted", "keystroke_violation", "system_dialog_parent_untrusted", "idle_timeout"], str]:
        """Verify action against envelope and consume one step quota if permitted.

        Returns:
            (allowed, reason, detail)
        """
        envelope = self.get_envelope(task_id)
        if not envelope:
            return False, "no_envelope", "No active intent envelope registered"

        now = time.monotonic()
        last_active = self._last_active_by_task.get(envelope.task_id, now)
        if envelope.idle_timeout_seconds > 0 and (now - last_active) > envelope.idle_timeout_seconds:
            logger.warning(
                "Envelope lease idle timeout exceeded (task=%s, idle=%.1fs > limit=%.1fs)",
                envelope.task_id,
                now - last_active,
                envelope.idle_timeout_seconds,
            )
            return False, "idle_timeout", f"Lease idle timed out (> {envelope.idle_timeout_seconds:.0f}s)"

        window = WindowHierarchyContext(
            app_name=app_name,
            app_id=app_id,
            window_title=window_title,
            parent_app_id=parent_app_id,
            is_system_dialog=is_system_dialog,
        )

        result = check_envelope_action(
            envelope=envelope,
            window=window,
            text_to_type=text_to_type,
        )

        if result.allowed:
            envelope.used_actions += 1
            self._last_active_by_task[envelope.task_id] = now
            logger.debug(
                "Envelope action granted without interruption (task=%s, used=%d/%d, app=%r)",
                envelope.task_id,
                envelope.used_actions,
                envelope.max_actions,
                app_name,
            )
            return True, "ok", ""

        logger.warning(
            "Envelope action boundary violation (task=%s, reason=%s, detail=%s)",
            envelope.task_id,
            result.reason,
            result.detail,
        )
        return False, result.reason, result.detail

    async def emit_progress(self, task_id: str | None = None) -> None:
        """Emit envelope progress update to frontend event stream."""
        envelope = self.get_envelope(task_id)
        if not envelope:
            return

        sink = get_tool_progress_sink()
        if not sink:
            return

        await sink.emit(
            {
                "type": AgentEventType.CUSTOM_EVENT,
                "data": {
                    "event_name": "desktop_envelope_progress",
                    "task_id": envelope.task_id,
                    "used_actions": envelope.used_actions,
                    "max_actions": envelope.max_actions,
                    "remaining_budget": envelope.remaining_budget(),
                    "can_extend": envelope.max_actions < _MAX_LEASE_HARD_LIMIT,
                    "hard_limit": _MAX_LEASE_HARD_LIMIT,
                },
            }
        )
