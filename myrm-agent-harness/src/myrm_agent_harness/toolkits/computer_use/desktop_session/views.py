"""WebUI view payloads of the desktop session: live updates and inspector exports.

[INPUT]
- host::DesktopSessionHost (POS: typed session state: registry, registry write entry, action lock, screen guard, view callback)
- perception.ax_dispatch::capture_snapshot, run_ax_call (POS: AX snapshot for the inspector refresh, awaited off the event loop on macOS)
- perception.overlay_roles::normalize_desktop_role (POS: cross-platform role normalization for the overlay payload)
- coordinate_scaler::CoordinateScaler (POS: maps element boxes onto the screenshot the inspector shows)
- som_overlay::apply_som_overlay_to_jpeg_base64, build_som_index_map (POS: numbered overlay on screenshots)

[OUTPUT]
- refs_for_view_update: @dref elements as the role / name / bbox / SoM-index payload the inspector overlay draws
- DesktopViewMixin: _emit_view_update, _emit_permission_view_update (live view events), _view_payload (the one payload
  shape of every view), _snapshot_screen_fields, _empty_view_payload, _annotate_screenshot_som, _observe_screen (the
  current screen drawn for display only), export_registry_view (what the agent registered, over the current screen),
  export_inspector_snapshot (the user's manual refresh: a new capture registered under the action lock)

[POS]
Everything the WebUI desktop inspector and the live view stream read from a DesktopSession. The inspector observes:
it never reads the accessibility tree on its own, registers a capture only on the user's manual refresh and then
through the single write entry under the action lock, and leaves the screenshot state the agent's coordinate actions
rely on as it found it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from myrm_agent_harness.toolkits.computer_use.coordinate_scaler import CoordinateScaler
from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import capture_snapshot, run_ax_call
from myrm_agent_harness.toolkits.computer_use.perception.overlay_roles import normalize_desktop_role
from myrm_agent_harness.toolkits.computer_use.som_overlay import (
    apply_som_overlay_to_jpeg_base64,
    build_som_index_map,
)

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)


def refs_for_view_update(
    refs: Mapping[str, ElementRef],
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


def _blank_meta(*, needs_permission: bool) -> SnapshotMeta:
    """The description of a view that shows no application."""
    return SnapshotMeta(
        ref_count=0, app_name="", window_title="", scope="foreground", needs_permission=needs_permission
    )


class DesktopViewMixin(DesktopSessionHost):
    """View-update emission and inspector exports."""

    def _snapshot_screen_fields(self) -> dict[str, int | float]:
        info = self.screen_info
        return {
            "screen_width": info.width,
            "screen_height": info.height,
            "dpi_scale": info.dpi_scale,
        }

    def _view_payload(
        self,
        *,
        screenshot_base64: str,
        screenshot_size: tuple[int, int],
        refs: Mapping[str, ElementRef],
        meta: SnapshotMeta,
        som_index_map: dict[str, int] | None,
    ) -> dict[str, object]:
        """One view as the WebUI reads it: the screenshot, the element overlay and the screen it was drawn on."""
        viewport_width = screenshot_size[0] or self.screen_info.width
        viewport_height = screenshot_size[1] or self.screen_info.height
        return {
            "screenshot_base64": screenshot_base64,
            "mime_type": "image/jpeg" if screenshot_base64 else "",
            "refs": refs_for_view_update(
                refs,
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

    def _empty_view_payload(self, *, needs_permission: bool) -> dict[str, object]:
        """Inspector payload without a screenshot or elements (permission missing, or the foreground app is blocked)."""
        return self._view_payload(
            screenshot_base64="",
            screenshot_size=(0, 0),
            refs={},
            meta=_blank_meta(needs_permission=needs_permission),
            som_index_map=None,
        )

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

    def _screen_unusable(self) -> bool:
        """Whether the screen is locked or the display sleeps. A passive read never asks the host to unlock it."""
        return self._screen_guard.is_locked() or self._screen_guard.is_sleeping()

    async def _observe_screen(
        self, refs: dict[str, ElementRef], som_index_map: dict[str, int]
    ) -> tuple[str, tuple[int, int]]:
        """The screen as the inspector shows it, numbered like the agent's screenshots; empty when it cannot be read.

        The image is made for display only: the scaler and the last screenshot that the coordinate actions
        convert the model's coordinates with stay as the agent left them.
        """
        if self._screen_unusable():
            return "", (0, 0)
        info = self.screen_info
        try:
            screenshot_b64, (sent_width, sent_height) = self._processor.process(await self._backend.screenshot(), info)
        except Exception as exc:
            logger.warning("[DESKTOP] Inspector screenshot capture failed: %s", exc)
            return "", (0, 0)
        scaler = CoordinateScaler(
            screen_width=info.width,
            screen_height=info.height,
            sent_width=sent_width,
            sent_height=sent_height,
            dpi_scale=info.dpi_scale,
        )
        return apply_som_overlay_to_jpeg_base64(screenshot_b64, refs, scaler, som_index_map), (sent_width, sent_height)

    async def _publish_view(self, payload: dict[str, object]) -> None:
        """Hand one view to the live-view callback and the tool event stream."""
        from myrm_agent_harness.core.events.types import AgentEventType
        from myrm_agent_harness.utils.runtime.progress_sink import (
            get_tool_progress_sink,
        )

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

    async def _emit_view_update(
        self,
        *,
        screenshot_base64: str,
        screenshot_size: tuple[int, int],
        refs: Mapping[str, ElementRef],
        meta: SnapshotMeta,
        som_index_map: dict[str, int] | None = None,
    ) -> None:
        await self._publish_view(
            self._view_payload(
                screenshot_base64=screenshot_base64,
                screenshot_size=screenshot_size,
                refs=refs,
                meta=meta,
                som_index_map=som_index_map,
            )
        )

    async def _emit_permission_view_update(self) -> None:
        await self._emit_view_update(
            screenshot_base64="",
            screenshot_size=(0, 0),
            refs={},
            meta=_blank_meta(needs_permission=True),
        )

    async def export_registry_view(self) -> dict[str, object] | None:
        """What the agent last registered, drawn over the current screen; None while it has registered nothing.

        A pure read: it never reads the accessibility tree, never writes the registry and never announces a view, so
        it may run while an action is in flight.
        """
        meta = self._refs.meta
        refs = self._refs.all_refs()
        if meta is None or not refs:
            return None
        generation = self._refs.generation
        som_index_map = build_som_index_map(refs)
        screenshot_b64, screenshot_size = await self._observe_screen(refs, som_index_map)
        return {
            **self._view_payload(
                screenshot_base64=screenshot_b64,
                screenshot_size=screenshot_size,
                refs=refs,
                meta=meta,
                som_index_map=som_index_map,
            ),
            "registry_generation": generation,
        }

    async def export_inspector_snapshot(self) -> dict[str, object] | None:
        """The user's manual refresh: read the foreground application anew and register it like an agent snapshot.

        The capture holds the action lock, so it never interleaves with an action. While an action holds the lock (an
        approval keeps it for as long as the user deliberates) or the screen is unusable, the answer is what the agent
        registered and nothing is written. A blocked application is not registered.
        """
        if self._action_lock.locked() or self._screen_unusable():
            return await self.export_registry_view()
        async with self._action_lock:
            return await self._capture_inspector_view()

    async def _capture_inspector_view(self) -> dict[str, object]:
        try:
            meta, refs = await run_ax_call(self._backend, capture_snapshot, self._backend, "foreground", None)
        except AXPermissionRequiredError:
            await self._emit_permission_view_update()
            return self._empty_view_payload(needs_permission=True)

        adopted = self._adopt_capture(meta, refs)
        if isinstance(adopted, str):
            return self._empty_view_payload(needs_permission=False)
        som_index_map = build_som_index_map(adopted.refs)
        screenshot_b64, screenshot_size = await self._observe_screen(adopted.refs, som_index_map)
        payload = self._view_payload(
            screenshot_base64=screenshot_b64,
            screenshot_size=screenshot_size,
            refs=adopted.refs,
            meta=meta,
            som_index_map=som_index_map,
        )
        await self._publish_view(payload)
        return payload
