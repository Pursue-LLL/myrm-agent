"""Safety support shared by the approval-gated desktop actions.

[INPUT]
- host::DesktopSessionHost (POS: typed session state: registry and its write entry, snapshot clock, screenshots)
- perception.ax_dispatch::capture_snapshot (POS: AX snapshot of the foreground or a target app)
- dref.errors::{AXTreeEmptyError, DRefStaleError} (POS: application window that cannot be read, unknown or retired @dref)

[OUTPUT]
- DesktopGuardSupportMixin: _revalidate_if_stale_after_approval (re-read the screen when a user approval delayed
  the action: the application the element was read from for an element action, a fresh screenshot for a vision
  action), _capture_guard_screenshot (evidence image for the approval cards of the semantic gate)

[POS]
Methods the interact and vision actions call once the user has approved, or while a guard asks for evidence.
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError, DRefStaleError
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import capture_snapshot

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)

_APPROVAL_REVALIDATION_THRESHOLD_SEC = 5.0


def _element_gone(interact_ref: str) -> str:
    return (
        "Safety Re-validation failed: The screen has changed significantly during approval. "
        f"The target element '@{interact_ref}' is no longer found. "
        "Please take a new snapshot to refresh the view and try again."
    )


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
                return self._reread_registered_app(interact_ref)

            shot = await self.take_screenshot()
            if not shot.success:
                return f"Safety Re-validation failed: Could not refresh screen state ({shot.error})."
            self._last_snapshot_time = time.time()
            return None
        except Exception as exc:
            return f"Safety Re-validation failed: Could not re-verify screen state ({exc!s})."

    def _reread_registered_app(self, interact_ref: str) -> str | None:
        """Read the application the element belongs to again; refuse unless the element is still in it.

        The application is the one the registry holds, not whichever is in front. A capture of another application
        or process is dropped without touching the registry, so the ids the model holds stay what they were.
        """
        ref_id = self._refs.normalize(interact_ref)
        try:
            registered = self._refs.resolve(ref_id).meta
        except DRefStaleError:
            return None  # an unknown reference is refused as stale by the caller
        try:
            meta, capture = capture_snapshot(self._backend, "target", registered.app_name)
        except AXTreeEmptyError:
            return _element_gone(ref_id)  # the application no longer has a window that can be read
        if not meta.same_app(registered):
            return _element_gone(ref_id)
        adopted = self._adopt_capture(meta, capture)
        if isinstance(adopted, str):
            return adopted
        if ref_id not in adopted.refs:
            return _element_gone(ref_id)
        self._last_snapshot_time = time.time()
        return None

    async def _capture_guard_screenshot(self) -> tuple[str, tuple[int, int]]:
        """Capture a guard-evidence screenshot (base64, image size) for HITL cards."""
        shot = await self.take_screenshot()
        if not shot.success:
            return "", (0, 0)
        return shot.screenshot_base64 or "", shot.screenshot_size
