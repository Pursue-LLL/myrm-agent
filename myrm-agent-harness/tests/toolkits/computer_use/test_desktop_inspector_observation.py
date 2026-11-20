"""The WebUI inspector observes the desktop: it never rewrites what the agent sees, holds or acts on.

The real DesktopSession, screen guard, screenshot processor and overlay run; only the OS boundary (the accessibility
read and the screen capture) is replaced.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from myrm_agent_harness.toolkits.computer_use.coordinate_scaler import CoordinateScaler
from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig, ScreenInfo

_PACKAGE = "myrm_agent_harness.toolkits.computer_use.desktop_session"
_INSPECTOR_CAPTURE = f"{_PACKAGE}.views.capture_snapshot"
_EVERY_CAPTURE = (_INSPECTOR_CAPTURE, f"{_PACKAGE}.snapshot.capture_snapshot", f"{_PACKAGE}.guards.capture_snapshot")
_SCREEN = ScreenInfo(width=1600, height=1000, dpi_scale=2.0)


def _screen_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (_SCREEN.width, _SCREEN.height), (200, 200, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _capture(*names: str, app: str = "Mail") -> tuple[SnapshotMeta, dict[str, ElementRef]]:
    """A raw capture as a platform script returns it."""
    meta = SnapshotMeta(ref_count=len(names), app_name=app, window_title="Inbox", scope="foreground", pid=100)
    refs = {
        f"d{i}": ElementRef(
            ref_id=f"d{i}",
            role="AXButton",
            name=name,
            bbox=BBox(100, 100 + 60 * i, 120, 40),
            backend_key=f"position-{i}",
        )
        for i, name in enumerate(names)
    }
    return meta, refs


def _numbered(payload: dict[str, object]) -> dict[str, object]:
    """The overlay number of every element by name."""
    refs = payload["refs"]
    assert isinstance(refs, dict)
    return {ref["name"]: ref["nth"] for ref in refs.values()}


def _screen_fields(payload: dict[str, object]) -> tuple[object, object, object]:
    return payload["screen_width"], payload["screen_height"], payload["dpi_scale"]


@pytest.fixture
def backend() -> MagicMock:
    backend = MagicMock()
    backend.screen_info.return_value = _SCREEN
    backend.screenshot = AsyncMock(return_value=_screen_png())
    return backend


@pytest.fixture
def seen() -> MagicMock:
    """Receiver of every view the session publishes."""
    return MagicMock()


@pytest.fixture
def session(backend: MagicMock, seen: MagicMock) -> DesktopSession:
    return DesktopSession(backend=backend, config=ComputerUseConfig(screenshot_delay=0.0), view_update_callback=seen)


@pytest.fixture
def agent_registered(session: DesktopSession) -> None:
    """The agent took a snapshot of Mail: two buttons are registered."""
    adopted = session._adopt_capture(*_capture("Reply", "Delete"))
    assert not isinstance(adopted, str)


@pytest.fixture
def no_ax_read() -> Iterator[MagicMock]:
    """Any read of the accessibility tree fails the test."""
    read = MagicMock(side_effect=AssertionError("the accessibility tree was read"))
    with ExitStack() as stack:
        for target in _EVERY_CAPTURE:
            stack.enter_context(patch(target, read))
        yield read


@pytest.mark.usefixtures("agent_registered")
class TestRegistryView:
    async def test_draws_what_the_agent_registered_over_the_current_screen(
        self, session: DesktopSession, backend: MagicMock
    ) -> None:
        plain, sent_size = session._processor.process(_screen_png(), _SCREEN)

        payload = await session.export_registry_view()

        assert payload is not None
        assert payload["screenshot_base64"] not in ("", plain)
        assert payload["mime_type"] == "image/jpeg"
        assert sent_size != (_SCREEN.width, _SCREEN.height)
        assert (payload["viewport_width"], payload["viewport_height"]) == sent_size
        assert _screen_fields(payload) == (_SCREEN.width, _SCREEN.height, _SCREEN.dpi_scale)
        assert _numbered(payload) == {"Reply": 1, "Delete": 2}
        assert payload["app_name"] == "Mail"
        assert payload["registry_generation"] == session.ref_registry.generation
        backend.screenshot.assert_awaited_once()

    async def test_never_reads_the_tree_nor_writes_the_registry(
        self, session: DesktopSession, no_ax_read: MagicMock
    ) -> None:
        refs, generation = session.ref_registry.all_refs(), session.ref_registry.generation

        await session.export_registry_view()

        no_ax_read.assert_not_called()
        assert session.ref_registry.all_refs() == refs
        assert session.ref_registry.generation == generation

    async def test_announces_nothing_on_the_view_stream(self, session: DesktopSession, seen: MagicMock) -> None:
        await session.export_registry_view()

        seen.assert_not_called()

    async def test_answers_while_an_action_holds_the_lock(self, session: DesktopSession) -> None:
        async with session._action_lock:
            payload = await asyncio.wait_for(session.export_registry_view(), timeout=5)

        assert payload is not None

    async def test_keeps_the_elements_and_drops_the_image_when_the_capture_fails(
        self, session: DesktopSession, backend: MagicMock
    ) -> None:
        backend.screenshot = AsyncMock(side_effect=OSError("screen recording denied"))

        payload = await session.export_registry_view()

        assert payload is not None
        assert payload["screenshot_base64"] == ""
        assert payload["mime_type"] == ""
        assert _numbered(payload) == {"Reply": 1, "Delete": 2}
        assert (payload["viewport_width"], payload["viewport_height"]) == (_SCREEN.width, _SCREEN.height)


class TestWithoutARegistry:
    async def test_the_registry_view_is_none_and_takes_no_screenshot(
        self, session: DesktopSession, backend: MagicMock
    ) -> None:
        assert await session.export_registry_view() is None
        backend.screenshot.assert_not_awaited()


@pytest.mark.parametrize("probe", ["is_screen_locked", "is_display_asleep"])
@pytest.mark.usefixtures("agent_registered")
class TestUnusableScreen:
    @pytest.fixture(autouse=True)
    def _screen_is_unusable(self, backend: MagicMock, probe: str) -> None:
        getattr(backend, probe).return_value = True

    @pytest.fixture
    def unlock(self, session: DesktopSession) -> AsyncMock:
        callback = AsyncMock(return_value=None)
        session.set_screen_unlock_callback(callback)
        return callback

    async def test_the_registry_view_has_no_image_and_never_unlocks_the_screen(
        self, session: DesktopSession, backend: MagicMock, unlock: AsyncMock
    ) -> None:
        payload = await session.export_registry_view()

        assert payload is not None
        assert payload["screenshot_base64"] == ""
        assert payload["refs"]
        backend.screenshot.assert_not_awaited()
        unlock.assert_not_awaited()

    async def test_a_manual_refresh_reads_nothing_new_and_never_unlocks_the_screen(
        self, session: DesktopSession, backend: MagicMock, unlock: AsyncMock, no_ax_read: MagicMock
    ) -> None:
        refs = session.ref_registry.all_refs()

        payload = await session.export_inspector_snapshot()

        assert payload is not None
        assert payload["screenshot_base64"] == ""
        assert payload["refs"]
        assert session.ref_registry.all_refs() == refs
        no_ax_read.assert_not_called()
        backend.screenshot.assert_not_awaited()
        unlock.assert_not_awaited()


class TestManualRefresh:
    async def test_registers_the_capture_under_the_action_lock(self, session: DesktopSession, seen: MagicMock) -> None:
        held: list[bool] = []

        def capture(*_args: object, **_kwargs: object) -> tuple[SnapshotMeta, dict[str, ElementRef]]:
            held.append(session._action_lock.locked())
            return _capture("Banner", "Reply")

        with patch(_INSPECTOR_CAPTURE, side_effect=capture):
            payload = await session.export_inspector_snapshot()

        assert held == [True]
        assert not session._action_lock.locked()
        assert payload is not None
        assert _numbered(payload) == {"Banner": 1, "Reply": 2}
        assert _screen_fields(payload) == (_SCREEN.width, _SCREEN.height, _SCREEN.dpi_scale)
        assert set(payload["refs"]) == set(session.ref_registry.all_refs())
        seen.assert_called_once_with(payload)

    @pytest.mark.usefixtures("agent_registered")
    async def test_while_an_action_holds_the_lock_it_answers_the_registry_and_writes_nothing(
        self, session: DesktopSession, no_ax_read: MagicMock
    ) -> None:
        registry_view = await session.export_registry_view()
        refs, generation = session.ref_registry.all_refs(), session.ref_registry.generation

        async with session._action_lock:
            payload = await asyncio.wait_for(session.export_inspector_snapshot(), timeout=5)

        assert payload == registry_view
        no_ax_read.assert_not_called()
        assert session.ref_registry.all_refs() == refs
        assert session.ref_registry.generation == generation

    async def test_while_an_action_holds_the_lock_and_nothing_is_registered_it_answers_nothing(
        self, session: DesktopSession, no_ax_read: MagicMock
    ) -> None:
        async with session._action_lock:
            payload = await asyncio.wait_for(session.export_inspector_snapshot(), timeout=5)

        assert payload is None
        no_ax_read.assert_not_called()

    async def test_releases_the_lock_when_the_capture_fails(self, session: DesktopSession) -> None:
        with patch(_INSPECTOR_CAPTURE, side_effect=RuntimeError("osascript failed")), pytest.raises(RuntimeError):
            await session.export_inspector_snapshot()

        assert not session._action_lock.locked()

    async def test_a_failed_screenshot_still_registers_the_capture(
        self, session: DesktopSession, backend: MagicMock
    ) -> None:
        backend.screenshot = AsyncMock(side_effect=OSError("screen recording denied"))

        with patch(_INSPECTOR_CAPTURE, return_value=_capture("Reply")):
            payload = await session.export_inspector_snapshot()

        assert payload is not None
        assert payload["screenshot_base64"] == ""
        assert _numbered(payload) == {"Reply": 1}
        assert len(session.ref_registry.all_refs()) == 1

    async def test_publishes_the_view_it_returns_in_the_shape_of_the_registry_view(
        self, session: DesktopSession, seen: MagicMock
    ) -> None:
        with patch(_INSPECTOR_CAPTURE, return_value=_capture("Reply")):
            refreshed = await session.export_inspector_snapshot()
        registry_view = await session.export_registry_view()

        assert refreshed is not None
        assert registry_view is not None
        assert registry_view.keys() == refreshed.keys() | {"registry_generation"}
        assert seen.call_args.args[0] == refreshed


@pytest.mark.usefixtures("agent_registered")
@pytest.mark.parametrize("export", ["export_registry_view", "export_inspector_snapshot"])
async def test_an_export_leaves_the_coordinate_mapping_of_the_agents_screenshot_alone(
    session: DesktopSession, export: str
) -> None:
    window_scaler = CoordinateScaler(
        screen_width=400, screen_height=300, sent_width=200, sent_height=150, dpi_scale=1.0, origin_x=120, origin_y=80
    )
    session._scaler = window_scaler
    session._last_screenshot_bytes = b"what the agent saw"

    with patch(_INSPECTOR_CAPTURE, return_value=_capture("Reply")):
        payload = await getattr(session, export)()

    assert payload is not None
    assert payload["screenshot_base64"]
    assert session.scaler is window_scaler
    assert session._last_screenshot_bytes == b"what the agent saw"
