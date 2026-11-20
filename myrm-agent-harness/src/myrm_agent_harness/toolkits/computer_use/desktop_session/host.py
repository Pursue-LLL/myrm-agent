"""Typed host contract of the DesktopSession mixins.

[INPUT]
- session::ComputerSession (POS: physical-input session base: screen guard, app approval, screenshots, coordinate input)
- dref.registry::DRefRegistry (POS: @dref registry the mixins read; it is written only through _adopt_capture)
- dref.types::ElementRef, SnapshotMeta, SnapshotScope (POS: element and snapshot types of the cross-mixin signatures)
- adopt::Adoption (POS: result of registering a capture)
- secrecy::FilledSecrets (POS: the secrets the vault filled, redacted from every capture before it is registered)

[OUTPUT]
- ViewUpdateCallback: receiver of the WebUI view payloads
- DesktopSessionHost: base of the snapshot, interact, vision, view and guard-support mixins; declares the state the
  DesktopSession aggregate root creates and the methods its mixins call on each other. Type-checking only: at
  runtime it is `object`, so the MRO of DesktopSession is unchanged.

[POS]
Single typed declaration of what a desktop mixin may rely on from its host, so a signature drift between two
mixins fails type checking instead of failing at runtime.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

ViewUpdateCallback = Callable[[dict[str, object]], None]

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.computer_use.dref.registry import DRefRegistry
    from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef, SnapshotMeta, SnapshotScope
    from myrm_agent_harness.toolkits.computer_use.session import ComputerSession

    from .adopt import Adoption
    from .secrecy import FilledSecrets

    class DesktopSessionHost(ComputerSession):
        _refs: DRefRegistry
        _filled_secrets: FilledSecrets
        _view_update_callback: ViewUpdateCallback | None
        _last_tree_text: str
        _last_snapshot_time: float
        _action_lock: asyncio.Lock

        async def desktop_snapshot(
            self,
            scope: SnapshotScope = "foreground",
            app_name: str | None = None,
            include_screenshot: bool = False,
            query: str | None = None,
            role: str | None = None,
            wait_seconds: float = 0.0,
        ) -> str | list[object]: ...

        def _adopt_capture(self, meta: SnapshotMeta, capture: Mapping[str, ElementRef]) -> Adoption | str: ...

        async def _revalidate_if_stale_after_approval(self, *, interact_ref: str | None = None) -> str | None: ...

        async def _capture_guard_screenshot(self) -> tuple[str, tuple[int, int]]: ...

        def _annotate_screenshot_som(
            self,
            screenshot_b64: str,
            refs: dict[str, ElementRef],
            som_index_map: dict[str, int] | None,
        ) -> str: ...

        async def _emit_view_update(
            self,
            *,
            screenshot_base64: str,
            screenshot_size: tuple[int, int],
            refs: Mapping[str, object],
            meta: object,
            som_index_map: dict[str, int] | None = None,
        ) -> None: ...

        async def _emit_permission_view_update(self) -> None: ...

else:
    DesktopSessionHost = object
