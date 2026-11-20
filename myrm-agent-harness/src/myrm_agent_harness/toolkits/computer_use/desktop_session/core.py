"""DesktopSession: semantic desktop control with an @dref registry.

[INPUT]
- snapshot, interact, vision, views, guards (POS: the mixins that implement the tool entry points and their support)
- session::ComputerSession, create_computer_session (POS: physical-input base the desktop session extends)
- dref.registry::DRefRegistry (POS: @dref registry owned by the session)

[OUTPUT]
- DesktopSession: AX snapshot, @dref registry, interact/vision, permissions, inspector export
- create_desktop_session(...) -> DesktopSession

[POS]
Aggregate root of the desktop tools: owns the registry, the snapshot clock and the action lock, and composes the mixins.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.toolkits.computer_use.dref.registry import DRefRegistry
from myrm_agent_harness.toolkits.computer_use.session import ComputerSession, create_computer_session
from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig, ForegroundPermissionCallback

from .guards import DesktopGuardSupportMixin
from .host import ViewUpdateCallback
from .interact import DesktopInteractMixin
from .snapshot import DesktopSnapshotMixin
from .views import DesktopViewMixin
from .vision import DesktopVisionMixin

logger = logging.getLogger(__name__)


class DesktopSession(
    DesktopInteractMixin,
    DesktopVisionMixin,
    DesktopSnapshotMixin,
    DesktopViewMixin,
    DesktopGuardSupportMixin,
    ComputerSession,
):
    """Computer session extended with AX snapshot, @dref registry, and view updates."""

    def __init__(
        self,
        backend: object,
        config: ComputerUseConfig | None = None,
        view_update_callback: ViewUpdateCallback | None = None,
        permission_callback: ForegroundPermissionCallback | None = None,
    ) -> None:
        super().__init__(backend=backend, config=config, permission_callback=permission_callback)  # type: ignore[arg-type]
        self._refs = DRefRegistry()
        self._view_update_callback = view_update_callback
        self._last_tree_text: str = ""
        self._last_snapshot_time: float = 0.0
        self._action_lock: asyncio.Lock = asyncio.Lock()

    @property
    def ref_registry(self) -> DRefRegistry:
        return self._refs

    def set_view_update_callback(self, callback: ViewUpdateCallback | None) -> None:
        self._view_update_callback = callback

    def reanchor_visual_state(self) -> None:
        """Clear cached AX refs, snapshots, and scaler to enforce re-anchoring upon wake."""
        super().reanchor_visual_state()
        self._refs.clear()
        self._last_snapshot_time = 0.0
        self._last_tree_text = ""
        logger.info("[REANCHOR] DesktopSession visual state cleared; next snapshot will refresh DOM/AX tree")


def create_desktop_session(
    config: ComputerUseConfig | None = None,
    view_update_callback: ViewUpdateCallback | None = None,
    permission_callback: ForegroundPermissionCallback | None = None,
) -> DesktopSession:
    base = create_computer_session(config=config)
    return DesktopSession(
        backend=base._backend,
        config=base._config,
        view_update_callback=view_update_callback,
        permission_callback=permission_callback,
    )
