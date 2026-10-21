"""Tests for DesktopCaptureTask: AX-driven capture loop feeding a recording session."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.recording.types import RecordedActionType

from app.services.skills.desktop_recording import DesktopCaptureTask
from app.services.skills.desktop_recording.state import RecordingSessionState


def _meta(app_name: str = "Finder", needs_permission: bool = False) -> SnapshotMeta:
    return SnapshotMeta(
        ref_count=1,
        app_name=app_name,
        window_title="Main",
        scope="foreground",
        needs_permission=needs_permission,
    )


def _element(ref_id: str, role: str = "AXButton", name: str = "Open") -> ElementRef:
    return ElementRef(
        ref_id=ref_id,
        role=role,
        name=name,
        bbox=BBox(0, 0, 10, 10),
        backend_key=ref_id,
    )


def test_marks_capture_unavailable_when_session_creation_fails() -> None:
    """A platform without AX support must degrade to manual entry instead of failing start."""
    session = RecordingSessionState(session_id="rec-1")
    task = DesktopCaptureTask(session)

    with patch.object(task, "_create_session", side_effect=RuntimeError("no AX backend")):
        task.start()

    assert session.capture_active is False
    assert session.capture_error is not None
    assert "desktop_capture_unavailable" in session.capture_error
    assert task.is_running is False


def test_capture_loop_appends_events_from_driver() -> None:
    """Observed interactions reach the session event list."""
    session = RecordingSessionState(session_id="rec-2")
    task = DesktopCaptureTask(session, poll_interval_sec=0.01)

    backend = MagicMock()
    # Same app throughout: an app switch would legitimately emit only window_focus, because a
    # newly focused app's elements are not interactions the user just performed.
    frames = [
        (_meta("Finder"), {"r1": _element("r1")}),
        (_meta("Finder"), {"r1": _element("r1"), "r2": _element("r2", name="Taxes")}),
        (_meta("Finder"), {"r1": _element("r1"), "r2": _element("r2", name="Taxes")}),
    ]
    calls = {"n": 0}

    def fake_capture(snapshot_backend: object, scope: str, app_name: str | None = None):
        index = min(calls["n"], len(frames) - 1)
        calls["n"] += 1
        return frames[index]

    async def run() -> None:
        with (
            patch.object(task, "_create_session", return_value=backend),
            patch(
                "myrm_agent_harness.toolkits.computer_use.recording.capture_driver.capture_snapshot",
                fake_capture,
            ),
        ):
            task.start()
            assert session.capture_active is True
            # Let the loop consume the scripted frames.
            for _ in range(50):
                if session.events:
                    break
                await asyncio.sleep(0.01)
            await task.stop()

    asyncio.run(run())

    assert session.events, "capture loop should have appended events"
    click = next(event for event in session.events if event.action == RecordedActionType.CLICK.value)
    assert click.element_title == "Taxes"
    assert click.element_role == "AXButton"
    assert task.is_running is False


def test_capture_loop_records_permission_requirement() -> None:
    """A permission-denied frame surfaces as capture_error while the loop stays alive."""
    session = RecordingSessionState(session_id="rec-3")
    task = DesktopCaptureTask(session, poll_interval_sec=0.01)
    backend = MagicMock()

    async def run() -> None:
        with (
            patch.object(task, "_create_session", return_value=backend),
            patch(
                "myrm_agent_harness.toolkits.computer_use.recording.capture_driver.capture_snapshot",
                return_value=(_meta("", needs_permission=True), {}),
            ),
        ):
            task.start()
            for _ in range(50):
                if session.capture_error:
                    break
                await asyncio.sleep(0.01)
            await task.stop()

    asyncio.run(run())

    assert session.capture_error == "desktop_capture_permission_required"


def test_permission_denied_pauses_then_resumes_when_granted() -> None:
    """A user who grants access while the dialog is open must keep their demonstration."""
    from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError

    session = RecordingSessionState(session_id="rec-5")
    task = DesktopCaptureTask(session, poll_interval_sec=0.01)
    backend = MagicMock()
    calls = {"n": 0}

    def deny_then_grant(backend_arg: object, scope: str, app_name: str | None = None):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise AXPermissionRequiredError("Accessibility permission required on macOS")
        return _meta("Finder"), {"r1": _element("r1", "AXButton", "Open")}

    async def run() -> None:
        with (
            patch.object(task, "_create_session", return_value=backend),
            patch(
                "myrm_agent_harness.toolkits.computer_use.recording.capture_driver.capture_snapshot",
                deny_then_grant,
            ),
        ):
            task.start()
            for _ in range(80):
                if session.capture_active and session.capture_error is None and calls["n"] > 2:
                    break
                await asyncio.sleep(0.01)
            await task.stop()

    asyncio.run(run())

    # Capture kept polling through the denial and resumed once access was granted.
    assert calls["n"] > 2
    assert session.capture_error is None


def test_permission_denied_releases_session_after_the_grace_window() -> None:
    """Waiting forever would leave the UI implying a recording that can never happen."""
    from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError

    session = RecordingSessionState(session_id="rec-6")
    task = DesktopCaptureTask(session, poll_interval_sec=0.01)
    backend = MagicMock()
    calls = {"n": 0}

    def always_deny(backend_arg: object, scope: str, app_name: str | None = None):
        calls["n"] += 1
        raise AXPermissionRequiredError("Accessibility permission required on macOS")

    async def run() -> None:
        with (
            patch.object(task, "_create_session", return_value=backend),
            patch(
                "myrm_agent_harness.toolkits.computer_use.recording.capture_driver.capture_snapshot",
                always_deny,
            ),
            patch(
                "app.services.skills.desktop_recording.capture_task._PERMISSION_GRACE_SEC",
                0.0,
            ),
        ):
            task.start()
            for _ in range(80):
                if not session.capture_active:
                    break
                await asyncio.sleep(0.01)

    asyncio.run(run())

    assert session.capture_active is False
    assert session.capture_error == "desktop_capture_permission_required"
    assert task.is_running is False


def test_reports_unsupported_deployment_without_starting_capture() -> None:
    """A headless deployment has no desktop; report that instead of an unusable permission ask."""
    session = RecordingSessionState(session_id="rec-6")
    task = DesktopCaptureTask(session)

    with patch.object(task, "_deploy_supports_capture", return_value=False):
        task.start()

    assert session.capture_active is False
    assert session.capture_error is not None
    assert "no desktop in this deployment" in session.capture_error
    assert task.is_running is False


def test_transient_tree_errors_do_not_stop_capture() -> None:
    """A briefly unreadable AX tree (app switch, system busy) must not end the recording."""
    from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError
    from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta

    session = RecordingSessionState(session_id="rec-7")
    task = DesktopCaptureTask(session, poll_interval_sec=0.01)
    backend = MagicMock()

    def _meta() -> SnapshotMeta:
        return SnapshotMeta(ref_count=1, app_name="Finder", window_title="Main", scope="foreground")

    def _element(ref_id: str) -> ElementRef:
        return ElementRef(
            ref_id=ref_id,
            role="AXButton",
            name="Open",
            bbox=BBox(0, 0, 10, 10),
            backend_key=ref_id,
        )

    calls = {"n": 0}

    def flaky_capture(backend_arg: object, scope: str, app_name: str | None = None):
        calls["n"] += 1
        # Fail once mid-recording, then resume normally with a newly added element.
        if calls["n"] == 2:
            raise AXTreeEmptyError("macOS AX snapshot timed out")
        if calls["n"] <= 3:
            return _meta(), {"r1": _element("r1")}
        return _meta(), {"r1": _element("r1"), "r2": _element("r2")}

    async def run() -> None:
        with (
            patch.object(task, "_create_session", return_value=backend),
            patch(
                "myrm_agent_harness.toolkits.computer_use.recording.capture_driver.capture_snapshot",
                flaky_capture,
            ),
        ):
            task.start()
            for _ in range(80):
                if session.events:
                    break
                await asyncio.sleep(0.01)
            await task.stop()

    asyncio.run(run())

    # The recording survived the transient failure and kept collecting interactions.
    assert session.events, "capture must continue after a transient AX failure"
    assert session.capture_error is None
    assert calls["n"] > 3


def test_abandoned_session_is_reaped() -> None:
    """A client that stopped polling (closed tab) must not leave capture running forever."""
    session = RecordingSessionState(session_id="rec-8")
    task = DesktopCaptureTask(session, poll_interval_sec=0.01)
    backend = MagicMock()
    # Simulate a client that vanished long ago.
    session.last_seen_at = 0.0

    async def run() -> None:
        with (
            patch.object(task, "_create_session", return_value=backend),
            patch(
                "myrm_agent_harness.toolkits.computer_use.recording.capture_driver.capture_snapshot",
                return_value=(_meta(), {"r1": _element("r1")}),
            ),
        ):
            task.start()
            for _ in range(60):
                if not session.capture_active:
                    break
                await asyncio.sleep(0.01)

    asyncio.run(run())

    assert session.capture_active is False
    assert session.capture_error == "desktop_capture_abandoned"
    assert task.is_running is False


def test_stop_is_safe_without_start() -> None:
    """Stopping a session that never started capture must not raise."""
    session = RecordingSessionState(session_id="rec-4")
    task = DesktopCaptureTask(session)

    asyncio.run(task.stop())

    assert task.is_running is False
