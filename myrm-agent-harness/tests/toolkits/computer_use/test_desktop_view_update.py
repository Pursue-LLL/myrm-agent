"""Tests for DesktopSession DESKTOP_VIEW_UPDATE emission."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.core.events.types import AgentEventType
from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.desktop_session.views import refs_for_view_update
from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef
from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig, ScreenContext, ScreenInfo
from myrm_agent_harness.utils.runtime import progress_sink


class _CaptureSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def emit(self, event: dict[str, object]) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_permission_error_emits_desktop_view_update() -> None:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    backend.screen_context.return_value = ScreenContext(active_window="Test", mouse_x=0, mouse_y=0)

    session = DesktopSession(backend=backend, config=ComputerUseConfig())
    sink = _CaptureSink()
    progress_sink.set_tool_progress_sink(sink)

    try:
        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.snapshot.capture_snapshot",
            side_effect=AXPermissionRequiredError("macOS"),
        ):
            result = await session.desktop_snapshot()

        assert isinstance(result, str)
        assert "Accessibility permission required" in result
        assert len(sink.events) == 1
        assert sink.events[0]["type"] == AgentEventType.DESKTOP_VIEW_UPDATE.value
        data = sink.events[0]["data"]
        assert isinstance(data, dict)
        assert data["needs_permission"] is True
    finally:
        progress_sink.set_tool_progress_sink(None)


def _ok_button() -> ElementRef:
    return ElementRef(
        ref_id="d0",
        role="AXButton",
        name="OK",
        bbox=BBox(x=10, y=20, width=80, height=30),
        backend_key="0",
    )


def test_refs_for_view_update_maps_som_index_and_bbox_payload() -> None:
    payload = refs_for_view_update(
        {"d0": _ok_button()},
        viewport_width=1920,
        viewport_height=1080,
        som_index_map={"d0": 3},
    )
    assert payload["d0"]["nth"] == 3
    assert payload["d0"]["bbox"]["viewport_width"] == 1920
    assert payload["d0"]["bbox"]["viewport_height"] == 1080
    assert payload["d0"]["bbox"]["centerX"] == 50


def test_refs_for_view_update_nth_is_none_without_som_index_map() -> None:
    payload = refs_for_view_update({"d0": _ok_button()}, viewport_width=1920, viewport_height=1080)
    assert payload["d0"]["nth"] is None
