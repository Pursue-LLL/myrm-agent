"""Tests for the single registry write entry of DesktopSession: ids that stay true and a guard no writer can skip."""

from __future__ import annotations

import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.types import ActionResult, ComputerUseConfig, ScreenInfo

_PACKAGE = "myrm_agent_harness.toolkits.computer_use.desktop_session"
_SNAPSHOT_CAPTURE = f"{_PACKAGE}.snapshot.capture_snapshot"
_REVALIDATION_CAPTURE = f"{_PACKAGE}.guards.capture_snapshot"
_INSPECTOR_CAPTURE = f"{_PACKAGE}.views.capture_snapshot"
_INVOKE = f"{_PACKAGE}.interact.invoke_element"


def _capture(*names: str, app: str = "Mail") -> tuple[SnapshotMeta, dict[str, ElementRef]]:
    """A raw capture as a platform script returns it: ids and locators are positions inside the capture."""
    meta = SnapshotMeta(ref_count=len(names), app_name=app, window_title="Inbox", scope="foreground", pid=100)
    refs = {
        f"d{i}": ElementRef(
            ref_id=f"d{i}",
            role="AXButton",
            name=name,
            bbox=BBox(0, 10 * i, 10, 10),
            backend_key=f"position-{i}",
        )
        for i, name in enumerate(names)
    }
    return meta, refs


def _id_of(session: DesktopSession, name: str) -> str:
    return next(ref_id for ref_id, element in session.ref_registry.all_refs().items() if element.name == name)


@pytest.fixture
def screenshot() -> AsyncMock:
    return AsyncMock(side_effect=OSError("no display"))


@pytest.fixture
def session(screenshot: AsyncMock) -> DesktopSession:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    backend.screenshot = screenshot
    return DesktopSession(backend=backend, config=ComputerUseConfig(screenshot_delay=0.0))


class TestStableIdsAcrossSnapshots:
    async def test_an_element_inserted_above_is_reported_as_the_only_change(self, session: DesktopSession) -> None:
        with patch(
            _SNAPSHOT_CAPTURE,
            side_effect=[_capture("Reply", "Delete", "Archive"), _capture("Banner", "Reply", "Delete", "Archive")],
        ):
            await session.desktop_snapshot()
            result = await session.desktop_snapshot()

        assert isinstance(result, str)
        assert "Desktop diff (1 change vs previous snapshot, app: Mail)" in result
        assert '+ @d3 AXButton "Banner"' in result
        assert "- @" not in result
        assert session.ref_registry.resolve("d1").element.name == "Delete"

    async def test_a_removed_element_is_reported_invalid_and_its_id_is_not_handed_to_its_neighbour(
        self, session: DesktopSession
    ) -> None:
        with patch(
            _SNAPSHOT_CAPTURE, side_effect=[_capture("Reply", "Delete", "Archive"), _capture("Reply", "Archive")]
        ):
            await session.desktop_snapshot()
            result = await session.desktop_snapshot()

        assert "- @d1 (removed, no longer valid)" in str(result)
        with patch(_INVOKE) as invoke:
            interact = await session.desktop_interact(ref="d1", action="click")
        assert "stale" in str(interact)
        assert "[REMEDY_HINT:" in str(interact)
        invoke.assert_not_called()
        assert session.ref_registry.resolve("d2").element.name == "Archive"

    async def test_an_unchanged_screen_says_every_id_is_still_valid(self, session: DesktopSession) -> None:
        with patch(_SNAPSHOT_CAPTURE, side_effect=[_capture("Reply", "Delete"), _capture("Reply", "Delete")]):
            await session.desktop_snapshot()
            result = await session.desktop_snapshot()

        assert "Desktop state unchanged" in str(result)
        assert "All @ids from the previous snapshot are still valid." in str(result)

    async def test_another_application_is_rendered_in_full_with_new_ids(self, session: DesktopSession) -> None:
        with patch(_SNAPSHOT_CAPTURE, side_effect=[_capture("Reply", app="Mail"), _capture("Reply", app="Safari")]):
            await session.desktop_snapshot()
            result = await session.desktop_snapshot()

        assert "Desktop diff" not in str(result)
        assert '@d1 AXButton "Reply"' in str(result)
        assert session.ref_registry.all_refs().keys() == {"d1"}

    async def test_a_snapshot_with_a_screenshot_renders_the_full_tree(self, session: DesktopSession) -> None:
        shot = ActionResult(success=True, screenshot_base64="", screenshot_size=(10, 10))
        with (
            patch(_SNAPSHOT_CAPTURE, side_effect=[_capture("Reply", "Delete"), _capture("Reply", "Delete")]),
            patch.object(session, "take_screenshot", AsyncMock(return_value=shot)),
        ):
            await session.desktop_snapshot()
            result = await session.desktop_snapshot(include_screenshot=True)

        assert "Desktop state unchanged" not in str(result)
        assert '@d0 AXButton "Reply"' in str(result)

    async def test_the_inspector_refresh_keeps_the_ids_the_agent_holds(self, session: DesktopSession) -> None:
        with patch(_SNAPSHOT_CAPTURE, return_value=_capture("Reply", "Delete")):
            await session.desktop_snapshot()
        delete_id = _id_of(session, "Delete")

        with patch(_INSPECTOR_CAPTURE, return_value=_capture("Banner", "Reply", "Delete")):
            payload = await session.export_inspector_snapshot()

        assert payload is not None
        refs = payload["refs"]
        assert isinstance(refs, dict)
        assert refs[delete_id]["name"] == "Delete"
        assert session.ref_registry.resolve(delete_id).element.name == "Delete"


class TestSensitiveAppGuardAtTheSingleWriteEntry:
    def test_a_blocked_capture_is_refused_and_leaves_the_registry_untouched(self, session: DesktopSession) -> None:
        meta, refs = _capture("Fill", app="1Password")
        generation = session.ref_registry.generation

        result = session._adopt_capture(meta, refs)

        assert isinstance(result, str)
        assert result.startswith("Safety: Blocked")
        assert session.ref_registry.generation == generation
        assert session.ref_registry.meta is None

    async def test_the_snapshot_does_not_register_a_blocked_app(self, session: DesktopSession) -> None:
        with patch(_SNAPSHOT_CAPTURE, return_value=_capture("Fill", app="1Password")):
            result = await session.desktop_snapshot()

        assert str(result).startswith("Safety: Blocked")
        assert session.ref_registry.all_refs() == {}

    async def test_the_revalidation_does_not_register_a_blocked_page_of_the_same_application(
        self, session: DesktopSession
    ) -> None:
        with patch(_SNAPSHOT_CAPTURE, return_value=_capture("Reply", app="Safari")):
            await session.desktop_snapshot()
        reply_id = _id_of(session, "Reply")
        session._last_snapshot_time = time.time() - 10.0
        meta, refs = _capture("Fill", app="Safari")
        vault_page = replace(meta, window_title="1Password")

        with patch(_REVALIDATION_CAPTURE, return_value=(vault_page, refs)), patch(_INVOKE) as invoke:
            result = await session.desktop_interact(ref=reply_id, action="click")

        assert str(result).startswith("Safety: Blocked")
        invoke.assert_not_called()
        assert session.ref_registry.meta is not None
        assert session.ref_registry.meta.window_title == "Inbox"
        assert session.ref_registry.resolve(reply_id).element.name == "Reply"

    async def test_the_inspector_refresh_does_not_register_a_blocked_app(
        self, session: DesktopSession, screenshot: AsyncMock
    ) -> None:
        with patch(_INSPECTOR_CAPTURE, return_value=_capture("Fill", app="1Password")):
            payload = await session.export_inspector_snapshot()

        assert payload is not None
        assert payload["refs"] == {}
        assert payload["app_name"] == ""
        assert payload["needs_permission"] is False
        screenshot.assert_not_awaited()
        assert session.ref_registry.all_refs() == {}

    async def test_a_blocked_app_leaves_the_previous_registry_in_place_for_the_inspector(
        self, session: DesktopSession
    ) -> None:
        with patch(_SNAPSHOT_CAPTURE, return_value=_capture("Reply", app="Mail")):
            await session.desktop_snapshot()
        reply_id = _id_of(session, "Reply")

        with patch(_INSPECTOR_CAPTURE, return_value=_capture("Fill", app="1Password")):
            await session.export_inspector_snapshot()

        assert session.ref_registry.resolve(reply_id).element.name == "Reply"
