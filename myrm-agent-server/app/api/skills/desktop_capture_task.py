"""Background desktop capture task driving a recording session's event stream.

[INPUT]
- myrm_agent_harness.toolkits.computer_use.desktop_session::create_desktop_session
- myrm_agent_harness.api::DesktopCaptureDriver
- app.api.skills.desktop_recorder_schemas::RecordingSessionState

[OUTPUT]
- DesktopCaptureTask: asyncio task that polls foreground AX snapshots and appends
  DesktopRecordedEvent entries to a RecordingSessionState until stopped

[POS]
Server business layer — turns a started recording session into a real capture loop, so the
desktop workflow recorder observes the demonstration instead of relying on hand-entered steps.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.api import DesktopCaptureDriver

from app.api.skills.desktop_recorder_schemas import RecordingSessionState

logger = logging.getLogger(__name__)

# Foreground AX capture is comparatively expensive (native tree walk per poll); ~0.7s keeps the
# event stream responsive without pinning a CPU core for the whole demonstration.
_DEFAULT_POLL_INTERVAL_SEC = 0.7


class DesktopCaptureTask:
    """Poll the foreground AX tree and append observed interactions to a session."""

    def __init__(
        self,
        session: RecordingSessionState,
        *,
        poll_interval_sec: float = _DEFAULT_POLL_INTERVAL_SEC,
    ) -> None:
        self._session = session
        self._poll_interval_sec = poll_interval_sec
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Launch the capture loop. Failures leave the session in manual-entry mode."""
        if self.is_running:
            return
        try:
            desktop_session = self._create_session()
        except Exception as exc:
            self._session.capture_error = f"desktop_capture_unavailable: {exc}"
            logger.warning("Desktop capture unavailable for session %s: %s", self._session.session_id, exc)
            return

        driver = DesktopCaptureDriver(
            desktop_session,
            app_scope=self._session.app_scope,
        )
        self._session.capture_active = True
        self._session.capture_error = None
        self._task = asyncio.create_task(self._run(driver))

    async def stop(self) -> None:
        """Cancel the capture loop and wait for it to unwind."""
        self._session.capture_active = False
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            # Expected: the loop is cancelled, not failed.
            pass
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Desktop capture task for %s ended with error: %s", self._session.session_id, exc)

    def _create_session(self) -> object:
        from myrm_agent_harness.toolkits.computer_use.desktop_session import (
            create_desktop_session,
        )

        return create_desktop_session()

    async def _run(self, driver: DesktopCaptureDriver) -> None:
        try:
            while True:
                # The first poll only primes the diff baseline; it intentionally emits nothing.
                frame = await driver.poll()
                if frame.meta.needs_permission:
                    self._session.capture_error = "desktop_capture_permission_required"
                for event in frame.events:
                    self._session.add_event(event)
                await asyncio.sleep(self._poll_interval_sec)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._session.capture_active = False
            self._session.capture_error = f"desktop_capture_failed: {exc}"
            logger.warning("Desktop capture loop stopped for %s: %s", self._session.session_id, exc)
