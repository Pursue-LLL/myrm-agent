"""StreamListener implementation for outbound WS/SSE connections.

Manages persistent outbound stream connections that listen for events
matching ``StreamTrigger`` configurations. Enables real-time monitoring
behind NAT (Local WebUI, Tauri desktop) where inbound webhooks fail.

[INPUT]
myrm_agent_harness.toolkits.cron.protocols::StreamListener, StreamEventCallback (POS: Protocols for the cron toolkit.)
myrm_agent_harness.toolkits.cron.triggers::StreamTrigger, StreamProtocol, validate_regex_pattern (POS: Trigger type definitions and security helpers.)
myrm_agent_harness.core.security.guards.ssrf::async_validate_url_for_ssrf (POS: Async outbound URL SSRF protection.)

[OUTPUT]
StreamListenerManager: Concrete StreamListener with WS/SSE support, reconnection, and resource limits.
extract_json_path: Minimal dotted-path JSONPath extraction (shared with PollListenerManager).

[POS]
Outbound stream connection manager for real-time event triggers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

import aiohttp

from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf
from myrm_agent_harness.toolkits.cron.protocols import StreamEventCallback
from myrm_agent_harness.toolkits.cron.triggers import (
    StreamProtocol,
    StreamTrigger,
    validate_regex_pattern,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_STREAMS = 10
_RECONNECT_BASE_SECONDS = 2.0
_RECONNECT_MAX_SECONDS = 300.0
_WS_PING_INTERVAL = 30.0
_WS_PING_TIMEOUT = 10.0


def extract_json_path(data: str, json_path: str) -> str | None:
    """Minimal JSONPath extraction (supports ``$.field.nested`` dotted paths).

    Returns the stringified value at the path, or None if extraction fails.
    Full JSONPath libraries are intentionally avoided to keep dependencies
    minimal — dotted-path covers >95% of real-world stream filter use cases.
    """
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None

    path = json_path.lstrip("$").lstrip(".")
    for key in path.split("."):
        if not key:
            continue
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list):
            try:
                obj = obj[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if obj is None:
            return None

    return str(obj)


class StreamListenerManager:
    """Manages outbound WS/SSE stream connections for real-time event triggers.

    Thread-safe via asyncio; all methods must be called from the same event loop.
    """

    def __init__(self, *, max_concurrent_streams: int = _DEFAULT_MAX_STREAMS) -> None:
        self._max_streams = max_concurrent_streams
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._urls: dict[str, str] = {}
        self._session: aiohttp.ClientSession | None = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def start_stream(
        self,
        job_id: str,
        trigger: StreamTrigger,
        on_event: StreamEventCallback,
    ) -> None:
        result = await async_validate_url_for_ssrf(trigger.url)
        if not result.safe:
            raise ValueError(f"Stream URL blocked (SSRF): {result.error}")

        if job_id in self._tasks:
            await self.stop_stream(job_id)

        if len(self._tasks) >= self._max_streams:
            raise ValueError(
                f"Max concurrent streams reached ({self._max_streams}). "
                "Stop an existing stream before starting a new one."
            )

        compiled_regex: re.Pattern[str] | None = None
        if trigger.filter_regex:
            compiled_regex = validate_regex_pattern(trigger.filter_regex)

        if trigger.protocol == StreamProtocol.WS:
            task = asyncio.create_task(
                self._ws_loop(job_id, trigger, on_event, compiled_regex),
                name=f"stream-ws-{job_id}",
            )
        else:
            task = asyncio.create_task(
                self._sse_loop(job_id, trigger, on_event, compiled_regex),
                name=f"stream-sse-{job_id}",
            )

        self._tasks[job_id] = task
        self._urls[job_id] = trigger.url
        logger.info("Stream started for job %s → %s (%s)", job_id, trigger.url, trigger.protocol.value)

    async def stop_stream(self, job_id: str) -> None:
        task = self._tasks.pop(job_id, None)
        self._urls.pop(job_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Stream stopped for job %s", job_id)

    async def stop_all(self) -> None:
        job_ids = list(self._tasks.keys())
        for job_id in job_ids:
            await self.stop_stream(job_id)
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def active_streams(self) -> dict[str, str]:
        return dict(self._urls)

    async def _ws_loop(
        self,
        job_id: str,
        trigger: StreamTrigger,
        on_event: StreamEventCallback,
        compiled_regex: re.Pattern[str] | None,
    ) -> None:
        backoff = _RECONNECT_BASE_SECONDS
        session = self._ensure_session()

        while True:
            try:
                async with session.ws_connect(
                    trigger.url,
                    headers=trigger.headers or None,
                    heartbeat=_WS_PING_INTERVAL,
                    receive_timeout=_WS_PING_TIMEOUT + _WS_PING_INTERVAL,
                ) as ws:
                    backoff = _RECONNECT_BASE_SECONDS
                    logger.debug("WS connected for job %s", job_id)

                    async for msg in ws:
                        if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                            raw = msg.data if isinstance(msg.data, str) else msg.data.decode()
                            await self._process_message(
                                job_id, trigger, on_event, compiled_regex, raw,
                            )
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.warning("WS error for job %s: %s", job_id, ws.exception())
                            break
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                            break

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "WS connection failed for job %s (retry in %.1fs): %s",
                    job_id, backoff, exc,
                )

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _RECONNECT_MAX_SECONDS)

    async def _sse_loop(
        self,
        job_id: str,
        trigger: StreamTrigger,
        on_event: StreamEventCallback,
        compiled_regex: re.Pattern[str] | None,
    ) -> None:
        backoff = _RECONNECT_BASE_SECONDS
        session = self._ensure_session()

        while True:
            try:
                async with session.get(
                    trigger.url,
                    headers={**(trigger.headers or {}), "Accept": "text/event-stream"},
                ) as resp:
                    resp.raise_for_status()
                    backoff = _RECONNECT_BASE_SECONDS
                    logger.debug("SSE connected for job %s", job_id)

                    data_buf: list[str] = []
                    async for line_bytes in resp.content:
                        line = line_bytes.decode().rstrip("\r\n")
                        if line.startswith(":"):
                            continue
                        if not line:
                            if data_buf:
                                data = "\n".join(data_buf)
                                data_buf.clear()
                                await self._process_message(
                                    job_id, trigger, on_event, compiled_regex, data,
                                )
                            continue
                        if line.startswith("data:"):
                            data_buf.append(line[5:].lstrip(" ") if len(line) > 5 else "")
                        elif line.startswith("event:") or line.startswith("id:") or line.startswith("retry:"):
                            pass

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "SSE connection failed for job %s (retry in %.1fs): %s",
                    job_id, backoff, exc,
                )

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _RECONNECT_MAX_SECONDS)

    async def _process_message(
        self,
        job_id: str,
        trigger: StreamTrigger,
        on_event: StreamEventCallback,
        compiled_regex: re.Pattern[str] | None,
        raw: str,
    ) -> None:
        value = raw
        if trigger.filter_json_path:
            extracted = extract_json_path(raw, trigger.filter_json_path)
            if extracted is None:
                return
            value = extracted

        if compiled_regex and not compiled_regex.search(value):
            return

        try:
            await on_event(job_id, trigger.url, raw)
        except Exception:
            logger.exception("Stream event callback failed for job %s", job_id)
