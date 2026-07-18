"""@input: normalized memory brief status payload + control plane telemetry settings
@output: MemoryBriefStatusTelemetryDispatcher + enqueue/start/stop helpers
@pos: Server-side aggregated memory brief status telemetry batch dispatch to Control Plane ([S] sandbox only).
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import QueueEmpty
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.config.settings import settings
from app.schemas.control_plane import (
    MemoryBriefStatusBatchPayload,
    MemoryBriefStatusTelemetryAggregate,
    MemoryBriefStatusTelemetryEnvelope,
)

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS: float = 5.0
_ENDPOINT_PATH: str = "/api/telemetry/memory-brief-status/batch"
_DEFAULT_BATCH_SIZE: int = 32
_DEFAULT_FLUSH_INTERVAL_SECONDS: float = 3.0
_DEFAULT_QUEUE_SIZE: int = 512
_TELEMETRY_SUBJECT_HEADER: str = "X-Telemetry-Subject"
_LABEL_NONE: str = "none"


@dataclass(frozen=True)
class MemoryBriefStatusTelemetryEvent:
    """Compact per-turn labels used for aggregation and transport."""

    phase: str
    brief_state: str
    brief_reason: str
    brief_source: str
    injection_state: str
    injection_source: str
    injection_reason: str


@dataclass(frozen=True)
class MemoryBriefStatusTelemetryConfig:
    """Validated runtime config for memory brief status telemetry dispatch."""

    control_plane_url: str
    telemetry_token: str
    telemetry_subject: str
    batch_size: int
    flush_interval_seconds: float
    queue_size: int

    @classmethod
    def from_settings(cls) -> MemoryBriefStatusTelemetryConfig | None:
        cp = settings.control_plane
        telemetry = settings.memory_brief_status_telemetry
        control_plane_url = cp.url.strip()
        telemetry_token = cp.telemetry_token.get_secret_value()
        telemetry_subject = cp.telemetry_subject.strip()

        present_count = sum(bool(value) for value in (control_plane_url, telemetry_token, telemetry_subject))
        if present_count == 0:
            logger.info("Memory brief status telemetry disabled: no control plane telemetry configured")
            return None

        missing = [
            label
            for label, value in (
                ("CONTROL_PLANE_URL", control_plane_url),
                ("CONTROL_PLANE_TELEMETRY_TOKEN", telemetry_token),
                ("CONTROL_PLANE_TELEMETRY_SUBJECT", telemetry_subject),
            )
            if not value
        ]
        if missing:
            logger.warning(
                "Memory brief status telemetry disabled: missing required settings: %s",
                ", ".join(missing),
            )
            return None

        batch_size = telemetry.batch_size if telemetry.batch_size > 0 else _DEFAULT_BATCH_SIZE
        flush_interval = (
            telemetry.flush_interval_seconds if telemetry.flush_interval_seconds > 0 else _DEFAULT_FLUSH_INTERVAL_SECONDS
        )
        queue_size = telemetry.queue_size if telemetry.queue_size > 0 else _DEFAULT_QUEUE_SIZE

        return cls(
            control_plane_url=control_plane_url.rstrip("/"),
            telemetry_token=telemetry_token,
            telemetry_subject=telemetry_subject,
            batch_size=batch_size,
            flush_interval_seconds=flush_interval,
            queue_size=queue_size,
        )


class MemoryBriefStatusTelemetryDispatcher:
    """Bounded in-process dispatcher with batch aggregation and graceful shutdown."""

    def __init__(self, config: MemoryBriefStatusTelemetryConfig) -> None:
        self._config = config
        self._queue: asyncio.Queue[MemoryBriefStatusTelemetryEvent] = asyncio.Queue(maxsize=config.queue_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._stop_event.clear()
        self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS)
        self._worker_task = asyncio.create_task(self._run(), name="memory-brief-status-telemetry")
        logger.info(
            "Memory brief status telemetry dispatcher started: batch=%d interval=%.2fs queue=%d",
            self._config.batch_size,
            self._config.flush_interval_seconds,
            self._config.queue_size,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("Memory brief status telemetry dispatcher stopped")

    def enqueue(self, phase: str, payload: object) -> None:
        event = _build_memory_brief_status_event(phase, payload)
        if event is None:
            return

        if self._queue.full():
            try:
                dropped = self._queue.get_nowait()
            except QueueEmpty:
                dropped = None
            if dropped is not None:
                logger.warning(
                    "Memory brief status telemetry queue full; dropping oldest event phase=%s state=%s source=%s",
                    dropped.phase,
                    dropped.brief_state,
                    dropped.brief_source,
                )
        self._queue.put_nowait(event)

    async def _run(self) -> None:
        while True:
            batch = await self._collect_batch()
            if batch:
                await self._flush_batch(batch)

            if self._stop_event.is_set() and self._queue.empty():
                return

    async def _collect_batch(self) -> list[MemoryBriefStatusTelemetryEvent]:
        if self._stop_event.is_set() and self._queue.empty():
            return []

        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=self._config.flush_interval_seconds)
        except TimeoutError:
            return []

        batch = [first]
        deadline = asyncio.get_running_loop().time() + self._config.flush_interval_seconds
        while len(batch) < self._config.batch_size:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
            except TimeoutError:
                break
        return batch

    async def _flush_batch(self, batch: list[MemoryBriefStatusTelemetryEvent]) -> None:
        if self._client is None:
            return

        endpoint = f"{self._config.control_plane_url}{_ENDPOINT_PATH}"
        headers = {
            "X-Telemetry-Token": self._config.telemetry_token,
            _TELEMETRY_SUBJECT_HEADER: self._config.telemetry_subject,
        }

        aggregates: dict[MemoryBriefStatusTelemetryEvent, int] = {}
        for event in batch:
            aggregates[event] = aggregates.get(event, 0) + 1

        envelope = MemoryBriefStatusTelemetryEnvelope(
            telemetry_subject=self._config.telemetry_subject,
            timestamp=datetime.now(timezone.utc).isoformat(),
            aggregates=[
                MemoryBriefStatusTelemetryAggregate(
                    phase=event.phase,
                    brief_state=event.brief_state,
                    brief_reason=event.brief_reason,
                    brief_source=event.brief_source,
                    injection_state=event.injection_state,
                    injection_source=event.injection_source,
                    injection_reason=event.injection_reason,
                    count=count,
                )
                for event, count in aggregates.items()
            ],
        )
        payload = MemoryBriefStatusBatchPayload(events=[envelope]).model_dump()

        for attempt in range(2):
            try:
                response = await self._client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                return
            except httpx.HTTPError as exc:
                if attempt == 1:
                    logger.warning(
                        "Failed to flush %d memory brief status telemetry events to %s: %s",
                        len(batch),
                        endpoint,
                        exc,
                    )
                    return
                await asyncio.sleep(0.2)


def _normalize_label(raw: object) -> str:
    if not isinstance(raw, str):
        return _LABEL_NONE
    value = raw.strip()
    return value or _LABEL_NONE


def _build_memory_brief_status_event(phase: str, payload: object) -> MemoryBriefStatusTelemetryEvent | None:
    if not isinstance(payload, Mapping):
        return None
    normalized_phase = _normalize_label(phase)
    if normalized_phase == _LABEL_NONE:
        return None
    brief_state = _normalize_label(payload.get("state"))
    if brief_state == _LABEL_NONE:
        return None

    injection = payload.get("injection")
    injection_mapping = injection if isinstance(injection, Mapping) else {}
    return MemoryBriefStatusTelemetryEvent(
        phase=normalized_phase,
        brief_state=brief_state,
        brief_reason=_normalize_label(payload.get("reason")),
        brief_source=_normalize_label(payload.get("source")),
        injection_state=_normalize_label(injection_mapping.get("state")),
        injection_source=_normalize_label(injection_mapping.get("source")),
        injection_reason=_normalize_label(injection_mapping.get("reason")),
    )


_dispatcher: MemoryBriefStatusTelemetryDispatcher | None = None


async def start_memory_brief_status_telemetry_dispatcher() -> None:
    """Start the shared memory brief status telemetry dispatcher."""
    global _dispatcher

    if _dispatcher is not None:
        return

    config = MemoryBriefStatusTelemetryConfig.from_settings()
    if config is None:
        return

    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    await dispatcher.start()
    _dispatcher = dispatcher


async def stop_memory_brief_status_telemetry_dispatcher() -> None:
    """Stop the shared memory brief status telemetry dispatcher and flush pending data."""
    global _dispatcher

    if _dispatcher is None:
        return
    await _dispatcher.stop()
    _dispatcher = None


def enqueue_memory_brief_status_telemetry(*, phase: str, payload: object) -> None:
    """Enqueue a normalized memory brief status payload if dispatcher is active."""
    if _dispatcher is None:
        return
    _dispatcher.enqueue(phase, payload)


__all__ = [
    "MemoryBriefStatusTelemetryConfig",
    "MemoryBriefStatusTelemetryDispatcher",
    "MemoryBriefStatusTelemetryEvent",
    "enqueue_memory_brief_status_telemetry",
    "start_memory_brief_status_telemetry_dispatcher",
    "stop_memory_brief_status_telemetry_dispatcher",
]
