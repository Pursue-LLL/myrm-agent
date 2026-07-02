"""PollListener implementation for periodic URL change detection.

Manages periodic HTTP polling tasks that detect content changes and fire
cron jobs. Bridges the ``PollTrigger`` data model (harness layer) to
concrete I/O (server layer).

[INPUT]
myrm_agent_harness.toolkits.cron.triggers::PollTrigger (POS: Poll trigger data model.)
myrm_agent_harness.core.security.guards.ssrf::async_validate_url_for_ssrf (POS: Async outbound URL SSRF protection.)
app.core.cron.adapters.stream_listener::extract_json_path (POS: Shared dotted-path JSONPath extraction.)

[OUTPUT]
PollListenerManager: Periodic polling with content-hash change detection.

[POS]
Periodic URL polling manager for change-detection triggers.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

import aiohttp

from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf
from myrm_agent_harness.toolkits.cron.protocols import StreamEventCallback
from myrm_agent_harness.toolkits.cron.triggers import PollTrigger

from .stream_listener import extract_json_path

logger = logging.getLogger(__name__)

_DEFAULT_MAX_POLLS = 20
_MIN_INTERVAL_SECONDS = 60


class PollListenerManager:
    """Manages periodic HTTP polling tasks for change-detection triggers.

    Each ``PollTrigger`` gets its own asyncio task that polls at the
    configured interval, computes a content hash, and fires when the
    hash changes (if ``change_detection`` is enabled).
    """

    def __init__(self, *, max_concurrent_polls: int = _DEFAULT_MAX_POLLS) -> None:
        self._max_polls = max_concurrent_polls
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._urls: dict[str, str] = {}
        self._hashes: dict[str, str] = {}
        self._session: aiohttp.ClientSession | None = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def start_poll(
        self,
        job_id: str,
        trigger: PollTrigger,
        on_event: StreamEventCallback,
    ) -> None:
        result = await async_validate_url_for_ssrf(trigger.url)
        if not result.safe:
            raise ValueError(f"Poll URL blocked (SSRF): {result.error}")

        if job_id in self._tasks:
            await self.stop_poll(job_id)

        if len(self._tasks) >= self._max_polls:
            raise ValueError(
                f"Max concurrent polls reached ({self._max_polls}). "
                "Stop an existing poll before starting a new one."
            )

        interval = max(trigger.interval_seconds, _MIN_INTERVAL_SECONDS)

        task = asyncio.create_task(
            self._poll_loop(job_id, trigger, on_event, interval),
            name=f"poll-{job_id}",
        )
        self._tasks[job_id] = task
        self._urls[job_id] = trigger.url
        logger.info("Poll started for job %s → %s (every %ds)", job_id, trigger.url, interval)

    async def stop_poll(self, job_id: str) -> None:
        task = self._tasks.pop(job_id, None)
        self._urls.pop(job_id, None)
        self._hashes.pop(job_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Poll stopped for job %s", job_id)

    async def stop_all(self) -> None:
        job_ids = list(self._tasks.keys())
        for job_id in job_ids:
            await self.stop_poll(job_id)
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def active_polls(self) -> dict[str, str]:
        return dict(self._urls)

    async def _poll_loop(
        self,
        job_id: str,
        trigger: PollTrigger,
        on_event: StreamEventCallback,
        interval: int,
    ) -> None:
        session = self._ensure_session()

        while True:
            try:
                async with session.get(trigger.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    resp.raise_for_status()
                    body = await resp.text()

                value = body
                if trigger.json_path:
                    extracted = extract_json_path(body, trigger.json_path)
                    if extracted is not None:
                        value = extracted

                content_hash = hashlib.sha256(value.encode()).hexdigest()
                prev_hash = self._hashes.get(job_id)

                if trigger.change_detection:
                    if prev_hash is not None and content_hash != prev_hash:
                        await on_event(job_id, trigger.url, value)
                    self._hashes[job_id] = content_hash
                else:
                    await on_event(job_id, trigger.url, value)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Poll failed for job %s: %s", job_id, exc)

            await asyncio.sleep(interval)
