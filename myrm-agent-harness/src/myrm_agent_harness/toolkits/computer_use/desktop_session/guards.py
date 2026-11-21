"""Safety support shared by the approval-gated desktop actions.

[INPUT]
- host::DesktopSessionHost (POS: typed session state: registry and its write entry, snapshot clock, screenshots)
- perception.ax_dispatch::capture_snapshot, run_ax_call (POS: AX snapshot of a target app, awaited off the event loop on macOS)
- dref.errors::{AXTreeEmptyError, DRefStaleError} (POS: application window that cannot be read, unknown or retired @dref)

[OUTPUT]
- Revalidation: what the approval-delay check did (whether it read the screen again, and the refusal when that failed)
- DesktopGuardSupportMixin: _revalidate_if_stale_after_approval (re-read the screen when a user approval delayed
  the action: the application the element was read from for an element action, a fresh screenshot for a vision
  action), _capture_guard_screenshot (evidence image for the approval cards of the semantic gate)

[POS]
Methods the interact and vision actions call once the user has approved, or while a guard asks for evidence.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError, DRefStaleError
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import capture_snapshot, run_ax_call

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)

_APPROVAL_REVALIDATION_THRESHOLD_SEC = 5.0


@dataclass(frozen=True, slots=True)
class Revalidation:
    """What the approval-delay check did: whether it read the screen again, and why the action must stop if it failed."""

    triggered: bool
    refusal: str | None = None


_NOT_DUE = Revalidation(triggered=False)


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
    ) -> Revalidation:
        """Refresh desktop state when user approval delayed the operation."""
        elapsed = time.time() - self._last_snapshot_time
        if elapsed <= _APPROVAL_REVALIDATION_THRESHOLD_SEC:
            return _NOT_DUE

        logger.info(
            "[SECURITY] Re-validating desktop state after approval delay (delayed %.1fs)",
            elapsed,
        )
        try:
            refusal = await self._refresh_after_approval(interact_ref)
        except Exception as exc:
            refusal = f"Safety Re-validation failed: Could not re-verify screen state ({exc!s})."
        return Revalidation(triggered=True, refusal=refusal)

    async def _refresh_after_approval(self, interact_ref: str | None) -> str | None:
        """Read again what the approved action depends on; the refusal text, or None when it still holds."""
        if interact_ref is not None:
            return await self._reread_registered_app(interact_ref)

        shot = await self.take_screenshot()
        if not shot.success:
            return f"Safety Re-validation failed: Could not refresh screen state ({shot.error})."
        self._last_snapshot_time = time.time()
        return None

    async def _reread_registered_app(self, interact_ref: str) -> str | None:
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
            meta, capture = await run_ax_call(
                self._backend, capture_snapshot, self._backend, "target", registered.app_name
            )
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
