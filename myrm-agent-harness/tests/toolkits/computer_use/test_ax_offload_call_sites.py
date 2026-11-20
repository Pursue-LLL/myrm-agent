"""Every place a tool waits on the macOS accessibility API hands the wait to a worker thread, so a slow osascript read
never freezes the event loop, and keeps it inline on the other platforms.

The real DesktopSession, capture driver and dispatch helper run; only the leaf call (the AX read or the osascript probe)
is replaced by a recorder that remembers which thread ran it.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.recording.capture_driver import DesktopCaptureDriver
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ComputerUseConfig,
    IPhoneMirrorProbeResult,
    IPhoneMirrorState,
    ScreenInfo,
)

_PACKAGE = "myrm_agent_harness.toolkits.computer_use"
_SESSION = f"{_PACKAGE}.desktop_session"

_MAIL = SnapshotMeta(ref_count=1, app_name="Mail", window_title="Inbox", scope="target")
_OPEN = ElementRef(ref_id="c0", role="AXButton", name="Open", bbox=BBox(10, 20, 100, 30), backend_key="3")
_MIRROR = SnapshotMeta(
    ref_count=1, app_name="iPhone Mirroring", window_title="", scope="target", app_id="com.apple.ScreenContinuity"
)
_MIRROR_IDENTITY = {"app_name": "iPhone Mirroring", "window_title": "", "app_id": "com.apple.ScreenContinuity"}


class Recorder:
    """Stands in for a blocking leaf call and remembers the thread that ran it."""

    def __init__(self, result: object) -> None:
        self._result = result
        self.threads: list[int] = []

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.threads.append(threading.get_ident())
        return self._result


@pytest.fixture(params=["MacOSBackend", "WindowsBackend", "LinuxBackend"])
def platform(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def _backend(platform: str) -> MagicMock:
    backend = MagicMock()
    backend.__class__.__name__ = platform
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    return backend


def _session(platform: str) -> DesktopSession:
    session = DesktopSession(backend=_backend(platform), config=ComputerUseConfig(screenshot_delay=0.0))
    session._screen_guard = MagicMock()
    session._screen_guard.refusal = AsyncMock(return_value=None)
    session._ensure_not_user_takeover = AsyncMock()
    session._emit_view_update = AsyncMock()
    session.take_screenshot = AsyncMock(return_value=ActionResult(success=False, error="no display"))
    return session


def _ran_once_where_expected(recorder: Recorder, platform: str) -> None:
    """The call ran once, on a worker thread for macOS and on the loop thread for the other platforms."""
    assert len(recorder.threads) == 1
    on_the_loop_thread = recorder.threads[0] == threading.get_ident()
    assert on_the_loop_thread is (platform != "MacOSBackend")


class TestDesktopSessionCallSites:
    async def test_snapshot_capture(self, platform: str) -> None:
        session = _session(platform)
        capture = Recorder((_MAIL, {"c0": _OPEN}))

        with patch(f"{_SESSION}.snapshot.capture_snapshot", capture):
            await session.desktop_snapshot(scope="target", app_name="Mail")

        _ran_once_where_expected(capture, platform)

    async def test_iphone_mirror_probe_after_a_snapshot(self, platform: str) -> None:
        session = _session(platform)
        probe = Recorder(IPhoneMirrorProbeResult(state=IPhoneMirrorState.READY, is_supported=True, detail="ready"))

        with (
            patch(f"{_SESSION}.snapshot.capture_snapshot", Recorder((_MIRROR, {"c0": _OPEN}))),
            patch(f"{_SESSION}.snapshot.probe_iphone_mirror_state", probe),
        ):
            await session.desktop_snapshot(scope="target", app_name="iPhone Mirroring")

        _ran_once_where_expected(probe, platform)

    async def test_native_invoke_of_an_interaction(self, platform: str) -> None:
        session = _session(platform)
        (ref_id,) = session._refs.adopt({"c0": _OPEN}, _MAIL)
        session._last_snapshot_time = time.time()
        invoke = Recorder(AxInvokeResult.delivered("pressed"))

        with (
            patch(f"{_SESSION}.interact.invoke_element", invoke),
            patch.object(session, "desktop_snapshot", AsyncMock(return_value="follow-up")),
        ):
            reply = str(await session.desktop_interact(ref=ref_id, action="click"))

        assert f"Action 'click' on @{ref_id} succeeded." in reply
        _ran_once_where_expected(invoke, platform)

    async def test_inspector_export_capture(self, platform: str) -> None:
        session = _session(platform)
        capture = Recorder((_MAIL, {"c0": _OPEN}))

        with patch(f"{_SESSION}.views.capture_snapshot", capture):
            await session.export_inspector_snapshot()

        _ran_once_where_expected(capture, platform)

    async def test_reread_after_a_delayed_approval(self, platform: str) -> None:
        session = _session(platform)
        (ref_id,) = session._refs.adopt({"c0": _OPEN}, _MAIL)
        session._last_snapshot_time = 0.0
        reread = Recorder((_MAIL, {"c0": _OPEN}))

        with patch(f"{_SESSION}.guards.capture_snapshot", reread):
            outcome = await session._revalidate_if_stale_after_approval(interact_ref=ref_id)

        assert outcome is None
        _ran_once_where_expected(reread, platform)

    async def test_foreground_identity_of_a_vision_capture(self, platform: str) -> None:
        session = _session(platform)
        identity = Recorder({"app_name": "Notes", "window_title": "Todo", "app_id": "com.apple.Notes"})

        with patch(f"{_SESSION}.vision.inspect_backend", identity):
            reply = await session.desktop_vision_capture()

        assert reply == "Capture failed: no display"
        _ran_once_where_expected(identity, platform)

    async def test_identity_and_mirror_probe_of_a_vision_action(self, platform: str) -> None:
        session = _session(platform)
        identity = Recorder(_MIRROR_IDENTITY)
        probe = Recorder(
            IPhoneMirrorProbeResult(
                state=IPhoneMirrorState.BLOCKED_CONNECT_PROMPT,
                is_supported=True,
                detail="locked",
                remedy_hint="unlock the phone",
            )
        )

        with (
            patch(f"{_SESSION}.vision.inspect_backend", identity),
            patch(f"{_SESSION}.vision.probe_iphone_mirror_state", probe),
        ):
            reply = await session.desktop_vision_action("wait")

        assert reply == "Safety: unlock the phone"
        _ran_once_where_expected(identity, platform)
        _ran_once_where_expected(probe, platform)

    async def test_foreground_lookup_of_an_app_approval(self, platform: str) -> None:
        session = _session(platform)
        identity = Recorder({"app_name": "Notes", "window_title": "Todo", "app_id": "com.apple.Notes"})

        with patch(f"{_PACKAGE}.perception.ax_dispatch.inspect_backend", identity):
            await session.check_app_approval(app_name="", window_title="", operation="desktop_interact")

        _ran_once_where_expected(identity, platform)


class TestRegistryWriterThread:
    """Only the read leaves the loop thread: the capture is registered back on it, so the registry has one writer."""

    @staticmethod
    def _spy_on_registration(session: DesktopSession) -> list[int]:
        written_on: list[int] = []
        register = session._adopt_capture

        def spy(meta: SnapshotMeta, capture: dict[str, ElementRef]) -> object:
            written_on.append(threading.get_ident())
            return register(meta, capture)

        session._adopt_capture = spy  # type: ignore[method-assign]
        return written_on

    async def test_a_snapshot_is_registered_on_the_loop_thread(self, platform: str) -> None:
        session = _session(platform)
        written_on = self._spy_on_registration(session)

        with patch(f"{_SESSION}.snapshot.capture_snapshot", Recorder((_MAIL, {"c0": _OPEN}))):
            await session.desktop_snapshot(scope="target", app_name="Mail")

        assert written_on == [threading.get_ident()]

    async def test_a_reread_is_registered_on_the_loop_thread(self, platform: str) -> None:
        session = _session(platform)
        (ref_id,) = session._refs.adopt({"c0": _OPEN}, _MAIL)
        session._last_snapshot_time = 0.0
        written_on = self._spy_on_registration(session)

        with patch(f"{_SESSION}.guards.capture_snapshot", Recorder((_MAIL, {"c0": _OPEN}))):
            await session._revalidate_if_stale_after_approval(interact_ref=ref_id)

        assert written_on == [threading.get_ident()]

    async def test_an_inspector_export_is_registered_on_the_loop_thread(self, platform: str) -> None:
        session = _session(platform)
        written_on = self._spy_on_registration(session)

        with patch(f"{_SESSION}.views.capture_snapshot", Recorder((_MAIL, {"c0": _OPEN}))):
            await session.export_inspector_snapshot()

        assert written_on == [threading.get_ident()]


class TestRecordingCallSite:
    async def test_capture_of_a_recording_poll(self, platform: str) -> None:
        driver = DesktopCaptureDriver(_backend(platform))
        notes = SnapshotMeta(ref_count=0, app_name="Notes", window_title="", scope="foreground")
        capture = Recorder((notes, {}))

        with patch(f"{_PACKAGE}.recording.capture_driver.capture_snapshot", capture):
            frame = await driver.poll()

        assert frame.events == ()
        _ran_once_where_expected(capture, platform)
