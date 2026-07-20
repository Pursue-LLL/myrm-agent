"""@input: contract + dropped_store + flush + metrics (POS: memory_brief_telemetry subpackage)
@output: MemoryBriefStatusTelemetryDispatcher + singleton start/stop/enqueue API
@pos: Server-side memory brief status telemetry dispatch (bounded queue, worker loop). Sandbox Control Plane batch upload only.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from pathlib import Path

import httpx

from app.services.agent.memory_brief_telemetry import metrics as _metrics
from app.services.agent.memory_brief_telemetry.contract import (
    _PHASE_PERSIST,
    _PHASE_STREAM,
    MemoryBriefStatusTelemetryConfig,
    MemoryBriefStatusTelemetryEvent,
    build_memory_brief_status_event,
)
from app.services.agent.memory_brief_telemetry.dropped_store import MemoryBriefStatusDroppedStore
from app.services.agent.memory_brief_telemetry.flush import flush_memory_brief_status_batch

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS: float = 5.0


class MemoryBriefStatusTelemetryDispatcher:
    """Bounded in-process dispatcher with batch aggregation and graceful shutdown."""

    def __init__(self, config: MemoryBriefStatusTelemetryConfig) -> None:
        self._config = config
        self._stream_queue: deque[MemoryBriefStatusTelemetryEvent] = deque()
        self._persist_queue: deque[MemoryBriefStatusTelemetryEvent] = deque()
        self._pending_event = asyncio.Event()
        self._queued_count = 0
        self._worker_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._client: httpx.AsyncClient | None = None
        self._queued_stream_count = 0
        self._queued_persist_count = 0
        dropped_state_path = (
            Path(config.dropped_state_path).expanduser().resolve()
            if config.dropped_state_path
            else None
        )
        self._dropped_store = MemoryBriefStatusDroppedStore(dropped_state_path)
        self._queue_depth_metric = (
            _metrics.MEMORY_STATUS_QUEUE_DEPTH.labels(telemetry_subject=config.telemetry_subject)
            if _metrics.MEMORY_STATUS_QUEUE_DEPTH is not None
            else None
        )
        self._queue_fill_ratio_metric = (
            _metrics.MEMORY_STATUS_QUEUE_FILL_RATIO.labels(telemetry_subject=config.telemetry_subject)
            if _metrics.MEMORY_STATUS_QUEUE_FILL_RATIO is not None
            else None
        )
        self._update_queue_metrics()

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._stop_event.clear()
        self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS)
        self._worker_task = asyncio.create_task(self._run(), name="memory-brief-status-telemetry")
        logger.info(
            "Memory brief status telemetry dispatcher started: batch=%d interval=%.2fs queue=%d phases=%s",
            self._config.batch_size,
            self._config.flush_interval_seconds,
            self._config.queue_size,
            ",".join(sorted(self._config.allowed_phases)),
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None
        self._dropped_store.persist_if_needed(force=True)
        if self._client is not None and self._dropped_store.has_pending():
            try:
                await self._flush_batch([])
            except Exception:
                if _metrics.MEMORY_STATUS_FLUSH_EXCEPTIONS is not None:
                    _metrics.MEMORY_STATUS_FLUSH_EXCEPTIONS.labels(
                        telemetry_subject=self._config.telemetry_subject
                    ).inc()
                logger.warning(
                    "Memory brief status telemetry shutdown flush crashed unexpectedly",
                    exc_info=True,
                )
            pending_dropped = self._dropped_store.pending_event_count()
            if pending_dropped > 0:
                logger.warning(
                    "Memory brief status telemetry stopped with pending dropped aggregates unsent: dropped_events=%d",
                    pending_dropped,
                )
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("Memory brief status telemetry dispatcher stopped")

    def enqueue(self, phase: str, payload: object) -> None:
        event = build_memory_brief_status_event(
            phase,
            payload,
            allowed_phases=self._config.allowed_phases,
        )
        if event is None:
            return

        if self._is_full():
            if event.phase == _PHASE_STREAM and self._has_queued_phase(_PHASE_PERSIST):
                self._record_drop(
                    dropped_phase=event.phase,
                    incoming_phase=event.phase,
                )
                logger.warning(
                    "Memory brief status telemetry queue full; dropping incoming stream event to preserve persist event"
                )
                self._update_queue_metrics()
                return

            dropped = self._pop_oldest_for_incoming_phase(event.phase)

            if dropped is not None:
                self._record_drop(
                    dropped_phase=dropped.phase,
                    incoming_phase=event.phase,
                )
                logger.warning(
                    "Memory brief status telemetry queue full; dropping queued event phase=%s state=%s source=%s to admit incoming phase=%s",
                    dropped.phase,
                    dropped.brief_state,
                    dropped.brief_source,
                    event.phase,
                )
        self._push_event(event)
        self._on_event_enqueued(event)

    def _is_full(self) -> bool:
        return self._queued_count >= self._config.queue_size

    def _push_event(self, event: MemoryBriefStatusTelemetryEvent) -> None:
        if event.phase == _PHASE_PERSIST:
            self._persist_queue.append(event)
        else:
            self._stream_queue.append(event)
        self._queued_count += 1
        self._pending_event.set()

    def _pop_oldest_for_incoming_phase(
        self,
        incoming_phase: str,
    ) -> MemoryBriefStatusTelemetryEvent | None:
        dropped: MemoryBriefStatusTelemetryEvent | None = None

        if incoming_phase == _PHASE_PERSIST and self._stream_queue:
            dropped = self._stream_queue.popleft()
        elif incoming_phase == _PHASE_STREAM and self._stream_queue:
            dropped = self._stream_queue.popleft()
        elif self._persist_queue:
            dropped = self._persist_queue.popleft()
        elif self._stream_queue:
            dropped = self._stream_queue.popleft()

        if dropped is not None:
            self._on_event_dequeued(dropped)
        return dropped

    def _record_drop(self, *, dropped_phase: str, incoming_phase: str) -> None:
        self._dropped_store.record_drop(
            dropped_phase=dropped_phase,
            incoming_phase=incoming_phase,
        )
        if _metrics.MEMORY_STATUS_DROPPED is None:
            return
        _metrics.MEMORY_STATUS_DROPPED.labels(
            telemetry_subject=self._config.telemetry_subject,
            dropped_phase=dropped_phase,
            incoming_phase=incoming_phase,
        ).inc()

    def _has_queued_phase(self, phase: str) -> bool:
        if phase == _PHASE_STREAM:
            return self._queued_stream_count > 0
        if phase == _PHASE_PERSIST:
            return self._queued_persist_count > 0
        return False

    def _on_event_enqueued(self, event: MemoryBriefStatusTelemetryEvent) -> None:
        if event.phase == _PHASE_STREAM:
            self._queued_stream_count += 1
        elif event.phase == _PHASE_PERSIST:
            self._queued_persist_count += 1
        self._update_queue_metrics()

    def _on_event_dequeued(self, event: MemoryBriefStatusTelemetryEvent) -> None:
        if event.phase == _PHASE_STREAM and self._queued_stream_count > 0:
            self._queued_stream_count -= 1
        elif event.phase == _PHASE_PERSIST and self._queued_persist_count > 0:
            self._queued_persist_count -= 1
        if self._queued_count > 0:
            self._queued_count -= 1
        if self._queued_count == 0:
            self._pending_event.clear()
        self._update_queue_metrics()

    def _update_queue_metrics(self) -> None:
        queue_depth = self._queued_count
        if self._queue_depth_metric is not None:
            self._queue_depth_metric.set(queue_depth)
        if self._queue_fill_ratio_metric is not None:
            capacity = self._config.queue_size if self._config.queue_size > 0 else 1
            self._queue_fill_ratio_metric.set(queue_depth / capacity)

    async def _run(self) -> None:
        while True:
            batch = await self._collect_batch()
            flush_dropped_only = not batch and self._dropped_store.has_pending()
            if batch or flush_dropped_only:
                try:
                    await self._flush_batch(batch)
                except Exception:
                    if _metrics.MEMORY_STATUS_FLUSH_EXCEPTIONS is not None:
                        _metrics.MEMORY_STATUS_FLUSH_EXCEPTIONS.labels(
                            telemetry_subject=self._config.telemetry_subject
                        ).inc()
                    logger.warning(
                        "Memory brief status telemetry flush loop crashed on unexpected error; dropping batch_size=%d",
                        len(batch),
                        exc_info=True,
                    )
            self._dropped_store.persist_if_needed()

            if self._stop_event.is_set() and self._queued_count == 0:
                return

    async def _collect_batch(self) -> list[MemoryBriefStatusTelemetryEvent]:
        if self._stop_event.is_set() and self._queued_count == 0:
            return []

        try:
            await asyncio.wait_for(self._pending_event.wait(), timeout=self._config.flush_interval_seconds)
        except TimeoutError:
            return []
        first = self._pop_next_event()
        if first is None:
            return []

        batch = [first]
        deadline = asyncio.get_running_loop().time() + self._config.flush_interval_seconds
        while len(batch) < self._config.batch_size:
            next_event = self._pop_next_event()
            if next_event is not None:
                batch.append(next_event)
                continue

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(self._pending_event.wait(), timeout=remaining)
            except TimeoutError:
                break
        return batch

    def _pop_next_event(self) -> MemoryBriefStatusTelemetryEvent | None:
        event: MemoryBriefStatusTelemetryEvent | None = None
        if self._persist_queue:
            event = self._persist_queue.popleft()
        elif self._stream_queue:
            event = self._stream_queue.popleft()
        if event is None:
            return None
        self._on_event_dequeued(event)
        return event

    async def _flush_batch(self, batch: list[MemoryBriefStatusTelemetryEvent]) -> None:
        if self._client is None:
            return
        await flush_memory_brief_status_batch(
            client=self._client,
            config=self._config,
            batch=batch,
            dropped_store=self._dropped_store,
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
