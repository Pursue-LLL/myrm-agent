"""Safety support shared by the approval-gated desktop actions.

[INPUT]
- host::DesktopSessionHost (POS: typed session state: registry write entry, snapshot clock, screenshots)
- perception.ax_dispatch::capture_snapshot (POS: AX snapshot of the foreground or a target app)

[OUTPUT]
- DesktopGuardSupportMixin: _revalidate_if_stale_after_approval (re-read the screen when a user approval delayed
  the action), _capture_guard_screenshot (evidence image for the approval cards of the semantic gate)

[POS]
Methods the interact and vision actions call once the user has approved, or while a guard asks for evidence.
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import capture_snapshot

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)

_APPROVAL_REVALIDATION_THRESHOLD_SEC = 5.0


class DesktopGuardSupportMixin(DesktopSessionHost):
    """Approval-delay revalidation and guard-evidence screenshots."""

    async def _revalidate_if_stale_after_approval(
        self,
        *,
        interact_ref: str | None = None,
    ) -> str | None:
        """Refresh desktop state when user approval delayed the operation."""
        elapsed = time.time() - self._last_snapshot_time
        if elapsed <= _APPROVAL_REVALIDATION_THRESHOLD_SEC:
            return None

        logger.info(
            "[SECURITY] Re-validating desktop state after approval delay (delayed %.1fs)",
            elapsed,
        )
        try:
            if interact_ref is not None:
                meta, refs = capture_snapshot(self._backend, "foreground", None)
                adopted = self._adopt_capture(meta, refs)
                if isinstance(adopted, str):
                    return adopted
                if self._refs.normalize(interact_ref) not in adopted.refs:
                    return (
                        "Safety Re-validation failed: The screen has changed significantly during approval. "
                        f"The target element '@{interact_ref}' is no longer found. "
                        "Please take a new snapshot to refresh the view and try again."
                    )
                self._last_snapshot_time = time.time()
                return None

            shot = await self.take_screenshot()
            if not shot.success:
                return f"Safety Re-validation failed: Could not refresh screen state ({shot.error})."
            self._last_snapshot_time = time.time()
            return None
        except Exception as exc:
            return f"Safety Re-validation failed: Could not re-verify screen state ({exc!s})."

    async def _capture_guard_screenshot(self) -> tuple[str, tuple[int, int]]:
        """Capture a guard-evidence screenshot (base64, image size) for HITL cards."""
        shot = await self.take_screenshot()
        if not shot.success:
            return "", (0, 0)
        return shot.screenshot_base64 or "", shot.screenshot_size
