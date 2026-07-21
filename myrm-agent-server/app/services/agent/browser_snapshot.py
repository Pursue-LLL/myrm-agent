"""Browser snapshot collection shared by WebUI and mobile remote routes.

[POS]
Single source of truth for browser snapshot payload shape used by frontend
preview surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BrowserSnapshotUnavailableError(Exception):
    """Raised when a browser snapshot cannot be produced."""

    status_code: int
    error: str
    message: str

    def __str__(self) -> str:
        return self.message


def _build_refs_payload(snapshot_result: object) -> dict[str, dict[str, object]]:
    if isinstance(snapshot_result, str | tuple):
        return {}

    from myrm_agent_harness.toolkits.browser.session.snapshot_result import SnapshotResult

    if not isinstance(snapshot_result, SnapshotResult):
        return {}

    return {
        ref_id: {
            "role": info.role,
            "name": info.name,
            "nth": info.nth,
            "bbox": (
                {
                    "x": info.bbox.x,
                    "y": info.bbox.y,
                    "width": info.bbox.width,
                    "height": info.bbox.height,
                    "centerX": info.bbox.centerX,
                    "centerY": info.bbox.centerY,
                    "viewport_x": info.bbox.viewport_x,
                    "viewport_y": info.bbox.viewport_y,
                    "viewport_width": info.bbox.viewport_width,
                    "viewport_height": info.bbox.viewport_height,
                }
                if info.bbox
                else None
            ),
            "position": info.position,
        }
        for ref_id, info in snapshot_result.refs.items()
    }


def _resolve_viewport(refs_data: dict[str, dict[str, object]]) -> tuple[int, int]:
    viewport_width = 1280
    viewport_height = 720
    for info in refs_data.values():
        bbox = info.get("bbox")
        if isinstance(bbox, dict) and bbox.get("viewport_width"):
            viewport_width = int(bbox["viewport_width"])
            viewport_height = int(bbox["viewport_height"])
            break
    return viewport_width, viewport_height


async def collect_browser_snapshot_payload(*, session_id: str | None = None) -> dict[str, object]:
    """Return normalized browser snapshot payload for UI preview."""
    from myrm_agent_harness.toolkits.browser.session import BrowserSession

    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    session = gateway.get_active_browser_session(session_id=session_id)
    if session is None:
        raise BrowserSnapshotUnavailableError(
            status_code=404,
            error="no_active_browser",
            message="No active browser session",
        )

    if not isinstance(session, BrowserSession):
        raise BrowserSnapshotUnavailableError(
            status_code=404,
            error="invalid_session",
            message="Browser session type mismatch",
        )

    snapshot_result = await session.snapshot(include_bbox=True)
    refs_data = _build_refs_payload(snapshot_result)
    screenshot_b64 = await session.extract_screenshot(scale=1.0)

    page_url = ""
    page_title = ""
    try:
        tab_ctrl = getattr(session, "_tab_controller", None)
        if tab_ctrl is not None:
            page = tab_ctrl.get_active_page()
            if page is not None:
                page_url = page.url
                page_title = await page.title()
    except Exception:
        pass

    viewport_width, viewport_height = _resolve_viewport(refs_data)
    return {
        "screenshot_base64": screenshot_b64,
        "mime_type": "image/jpeg",
        "refs": refs_data,
        "page_url": page_url,
        "page_title": page_title,
        "viewport_width": viewport_width,
        "viewport_height": viewport_height,
    }


__all__ = ["BrowserSnapshotUnavailableError", "collect_browser_snapshot_payload"]
