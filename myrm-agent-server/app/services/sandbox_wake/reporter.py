"""Report the next must-wake time to the control plane (hosted sandboxes only).

[INPUT]
- app.config.settings::settings (POS: CONTROL_PLANE_URL / telemetry token / SANDBOX_ID)
- app.services.sandbox_wake.next_wake::earliest_scheduled_wake (POS: next parked-goal / cron / kanban time)

[OUTPUT]
- WakeScheduleReporter / get_wake_schedule_reporter: start / stop / report_once

[POS]
The idle recycler pauses a hosted sandbox's container, which freezes this process's timers (goal
usage-limit resume, cron, kanban un-schedule). So the control plane must wake the sandbox on time, and it can only do
that if told when. This reporter pushes the earliest such time whenever it changes (retrying
failed pushes) and repeats an unchanged one as a heartbeat, over the same sandbox-to-control-plane
HTTP channel used for entitlements. It re-checks the moment the reported time arrives, because
the control plane drops a trigger once it finds the sandbox awake and must then hear the next
time before an idle pause freezes this process. Without a configured control plane (local or
self-hosted) it does nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.config.settings import settings
from app.services.sandbox_wake.next_wake import earliest_scheduled_wake

logger = logging.getLogger(__name__)

_REPORT_INTERVAL_S = 30.0
# An unchanged time is pushed again this often: the control plane may have lost it (abandoned
# trigger, restored database) and this process cannot tell.
_HEARTBEAT_INTERVAL_S = 600.0
# Floor for the wait until the reported time, so a clock that lands just short of it cannot spin the loop.
_MIN_RECHECK_S = 2.0
_REQUEST_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class WakeScheduleEndpoint:
    """Where and how this sandbox reports its schedule to the control plane."""

    url: str
    headers: dict[str, str]

    @classmethod
    def from_settings(cls) -> WakeScheduleEndpoint | None:
        cp = settings.control_plane
        base = cp.url.strip().rstrip("/")
        token = cp.telemetry_token.get_secret_value().strip()
        sandbox_id = cp.sandbox_id.strip()
        if not (base and token and sandbox_id):
            return None
        return cls(
            url=f"{base}/api/internal/sandboxes/{sandbox_id}/wake-schedule",
            headers={"X-Telemetry-Token": token, "X-Sandbox-Id": sandbox_id},
        )


class WakeScheduleReporter:
    """Polls the next must-wake time and pushes it to the control plane when it changes or ages."""

    def __init__(
        self,
        endpoint: WakeScheduleEndpoint | None,
        *,
        interval: float = _REPORT_INTERVAL_S,
        heartbeat: float = _HEARTBEAT_INTERVAL_S,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._endpoint = endpoint
        self._interval = interval
        self._heartbeat = heartbeat
        self._clock = clock
        self._reported: float | None = None
        self._has_reported = False
        self._last_push_at = 0.0
        self._push_failing = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._endpoint is None:
            logger.debug("Wake schedule reporter disabled: sandbox has no control plane configured")
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="wake-schedule-reporter")
        logger.info("Wake schedule reporter started (interval=%.0fs)", self._interval)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def report_once(self) -> bool:
        """Push the current next-wake time if it changed or the last accepted push is a heartbeat old.

        False on push failure.
        """
        now = self._clock()
        target = await earliest_scheduled_wake(now)
        if self._has_reported and target == self._reported and now - self._last_push_at < self._heartbeat:
            return True
        if not await self._push(target):
            return False
        self._reported = target
        self._has_reported = True
        self._last_push_at = now
        return True

    def _delay_until_next_check(self) -> float:
        """Seconds until the next check: no later than the reported time itself.

        A goal / cron time is reported ahead of its due time; once it arrives the earliest schedule
        moves on, and the control plane must hear the new one before an idle pause can freeze us.
        """
        if self._reported is None:
            return self._interval
        return min(self._interval, max(self._reported - self._clock(), _MIN_RECHECK_S))

    async def _run(self) -> None:
        while True:
            delay = self._interval
            try:
                if await self.report_once():
                    delay = self._delay_until_next_check()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Wake schedule report failed", exc_info=True)
            await asyncio.sleep(delay)

    async def _push(self, next_wake_at: float | None) -> bool:
        if self._endpoint is None:
            return False
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
                response = await client.put(
                    self._endpoint.url,
                    json={"next_wake_at": next_wake_at},
                    headers=self._endpoint.headers,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            if not self._push_failing:
                logger.warning("Could not report wake schedule to the control plane: %s", exc)
            self._push_failing = True
            return False
        self._push_failing = False
        return True


_reporter: WakeScheduleReporter | None = None


def get_wake_schedule_reporter() -> WakeScheduleReporter:
    global _reporter
    if _reporter is None:
        _reporter = WakeScheduleReporter(WakeScheduleEndpoint.from_settings())
    return _reporter
