"""WebUI view payloads of the desktop session: live updates and inspector exports.

[INPUT]
- host::DesktopSessionHost (POS: typed session state: registry, view callback, screenshots)
- perception.ax_dispatch::capture_snapshot (POS: AX snapshot for the inspector refresh)
- perception.overlay_roles::normalize_desktop_role (POS: cross-platform role normalization for the overlay payload)
- som_overlay::apply_som_overlay_to_jpeg_base64, build_som_index_map (POS: numbered overlay on screenshots)

[OUTPUT]
- refs_for_view_update: @dref elements as the role / name / bbox / SoM-index payload the inspector overlay draws
- DesktopViewMixin: _emit_view_update, _emit_permission_view_update (live view events), _snapshot_screen_fields,
  _annotate_screenshot_som (payload parts), export_registry_view (last registry without a new capture),
  export_inspector_snapshot (fresh foreground capture for the inspector)

[POS]
Everything the WebUI desktop inspector and the live view stream read from a DesktopSession.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import capture_snapshot
from myrm_agent_harness.toolkits.computer_use.perception.overlay_roles import normalize_desktop_role
from myrm_agent_harness.toolkits.computer_use.som_overlay import (
    apply_som_overlay_to_jpeg_base64,
    build_som_index_map,
)
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)


def refs_for_view_update(
    refs: dict[str, ElementRef],
    *,
    viewport_width: int,
    viewport_height: int,
    som_index_map: dict[str, int] | None = None,
) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for ref_id, element in refs.items():
        nth: int | None = None
        if som_index_map is not None:
            nth = som_index_map.get(ref_id)
        payload[ref_id] = {
            "role": normalize_desktop_role(element.role),
            "name": element.name,
            "nth": nth,
            "bbox": {
                "x": element.bbox.x,
                "y": element.bbox.y,
                "width": element.bbox.width,
                "height": element.bbox.height,
                "centerX": element.bbox.center_x,
                "centerY": element.bbox.center_y,
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
            },
            "position": None,
        }
    return payload


class DesktopViewMixin(DesktopSessionHost):
    """View-update emission and inspector exports."""

    def _snapshot_screen_fields(self) -> dict[str, int | float]:
        info = self.screen_info
        return {
            "screen_width": info.width,
            "screen_height": info.height,
            "dpi_scale": info.dpi_scale,
        }

    def _annotate_screenshot_som(
        self,
        screenshot_b64: str,
        refs: dict[str, ElementRef],
        som_index_map: dict[str, int] | None,
    ) -> str:
        if not screenshot_b64 or not som_index_map or self.scaler is None:
            return screenshot_b64
        return apply_som_overlay_to_jpeg_base64(
            screenshot_b64,
            refs,
            self.scaler,
            som_index_map,
        )

    async def _emit_view_update(
        self,
        *,
        screenshot_base64: str,
        screenshot_size: tuple[int, int],
        refs: Mapping[str, object],
        meta: object,
        som_index_map: dict[str, int] | None = None,
    ) -> None:
        from myrm_agent_harness.core.events.types import AgentEventType
        from myrm_agent_harness.toolkits.computer_use.dref.types import (
            ElementRef,
            SnapshotMeta,
        )
        from myrm_agent_harness.utils.runtime.progress_sink import (
            get_tool_progress_sink,
        )

        assert isinstance(meta, SnapshotMeta)
        element_refs = {key: value for key, value in refs.items() if isinstance(value, ElementRef)}
        viewport_width = screenshot_size[0] or self.screen_info.width
        viewport_height = screenshot_size[1] or self.screen_info.height
        payload: dict[str, object] = {
            "screenshot_base64": screenshot_base64,
            "mime_type": "image/jpeg" if screenshot_base64 else "",
            "refs": refs_for_view_update(
                element_refs,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                som_index_map=som_index_map,
            ),
            "app_name": meta.app_name,
            "window_title": meta.window_title,
            "scope": meta.scope,
            "needs_permission": meta.needs_permission,
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            **self._snapshot_screen_fields(),
        }
        if self._view_update_callback is not None:
            self._view_update_callback(payload)

        sink = get_tool_progress_sink()
        if sink is not None:
            await sink.emit(
                {
                    "type": AgentEventType.DESKTOP_VIEW_UPDATE.value,
                    "data": payload,
                }
            )

    async def _emit_permission_view_update(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.dref.types import SnapshotMeta

        meta = SnapshotMeta(
            ref_count=0,
            app_name="",
            window_title="",
            scope="foreground",
            needs_permission=True,
        )
        await self._emit_view_update(
            screenshot_base64="",
            screenshot_size=(0, 0),
            refs={},
            meta=meta,
        )

    def export_registry_view(self) -> dict[str, object] | None:
        """Return last DRefRegistry snapshot for inspector/API without re-capturing AX."""
        from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef

        meta = self._refs.meta
        refs = self._refs.all_refs()
        if meta is None or not refs:
            return None
        element_refs = {key: value for key, value in refs.items() if isinstance(value, ElementRef)}
        if not element_refs:
            return None
        info = self.screen_info
        viewport_width = info.width
        viewport_height = info.height
        return {
            "screenshot_base64": "",
            "mime_type": "",
            "refs": refs_for_view_update(
                element_refs,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                som_index_map=None,
            ),
            "app_name": meta.app_name,
            "window_title": meta.window_title,
            "scope": meta.scope,
            "needs_permission": meta.needs_permission,
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            "registry_generation": self._refs.generation,
            **self._snapshot_screen_fields(),
        }

    async def export_inspector_snapshot(self) -> dict[str, object]:
        """Capture foreground desktop state for WebUI inspector refresh."""
        from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef

        try:
            meta, refs = capture_snapshot(self._backend, "foreground", None)
        except AXPermissionRequiredError:
            await self._emit_permission_view_update()
            info = self.screen_info
            return {
                "screenshot_base64": "",
                "mime_type": "",
                "refs": {},
                "app_name": "",
                "window_title": "",
                "scope": "foreground",
                "needs_permission": True,
                "viewport_width": info.width,
                "viewport_height": info.height,
                **self._snapshot_screen_fields(),
            }

        self._refs.replace(refs, meta)
        som_index_map = build_som_index_map(refs)
        try:
            shot = await self.take_screenshot()
        except Exception as exc:
            logger.warning("[DESKTOP] Inspector screenshot capture failed: %s", exc)
            shot = ActionResult(success=False, error=str(exc))
        screenshot_b64 = shot.screenshot_base64 if shot.success else ""
        screenshot_size = shot.screenshot_size if shot.success else (0, 0)
        element_refs = {key: value for key, value in refs.items() if isinstance(value, ElementRef)}
        if screenshot_b64:
            screenshot_b64 = self._annotate_screenshot_som(screenshot_b64, element_refs, som_index_map)
        viewport_width = screenshot_size[0] or self.screen_info.width
        viewport_height = screenshot_size[1] or self.screen_info.height

        await self._emit_view_update(
            screenshot_base64=screenshot_b64,
            screenshot_size=screenshot_size,
            refs=refs,
            meta=meta,
            som_index_map=som_index_map,
        )

        return {
            "screenshot_base64": screenshot_b64,
            "mime_type": "image/jpeg" if screenshot_b64 else "",
            "refs": refs_for_view_update(
                element_refs,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                som_index_map=som_index_map,
            ),
            "app_name": meta.app_name,
            "window_title": meta.window_title,
            "scope": meta.scope,
            "needs_permission": meta.needs_permission,
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            **self._snapshot_screen_fields(),
        }
