"""@input: contract + pending_store + flush (POS: memory_guardian_guard_telemetry subpackage)
@output: MemoryGuardianGuardTelemetryDispatcher + singleton start/stop/enqueue API
@pos: Server-side aggregated guardian guard-unavailable telemetry batch dispatch ([S] sandbox only).
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from pathlib import Path

import httpx

from app.services.agent.memory_guardian_guard_telemetry.contract import (
    MemoryGuardianGuardTelemetryConfig,
    MemoryGuardianGuardTelemetryEvent,
    _ALLOWED_FREQUENCY_TIERS,
    _ALLOWED_GUARDS,
    _ALLOWED_REASONS,
    normalize_governed_label,
)
from app.services.agent.memory_guardian_guard_telemetry.flush import (
    flush_guardian_guard_telemetry_envelopes,
    merge_aggregates,
    pending_event_count,
)
from app.services.agent.memory_guardian_guard_telemetry.pending_store import (
    MemoryGuardianGuardPendingStore,
)

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS: float = 5.0


class MemoryGuardianGuardTelemetryDispatcher:
    """Bounded in-process dispatcher with batch aggregation and graceful shutdown."""

    def __init__(self, config: MemoryGuardianGuardTelemetryConfig) -> None:
        self._config = config
        self._queue: deque[MemoryGuardianGuardTelemetryEvent] = deque()
        self._overflow_aggregates: dict[MemoryGuardianGuardTelemetryEvent, int] = {}
        pending_state_path = (
            Path(config.pending_state_path).expanduser().resolve()
            if config.pending_state_path
            else None
        )
        self._pending_store = MemoryGuardianGuardPendingStore(pending_state_path)
        self._pending_envelopes = deque(self._pending_store.load())
        self._pending_event = asyncio.Event()
        if self._pending_envelopes:
            self._pending_event.set()
        self._queued_count = 0
        self._worker_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._stop_event.clear()
        self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS)
        self._worker_task = asyncio.create_task(self._run(), name="memory-guardian-guard-telemetry")
        logger.info(
            "Guardian guard telemetry dispatcher started: batch=%d interval=%.2fs queue=%d",
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
        logger.info("Guardian guard telemetry dispatcher stopped")

    def enqueue(self, event: MemoryGuardianGuardTelemetryEvent) -> None:
        if self._queued_count >= self._config.queue_size and self._queue:
            dropped = self._queue.popleft()
            self._queued_count -= 1
            merge_aggregates(self._overflow_aggregates, {dropped: 1})
            logger.warning(
                "Guardian guard telemetry queue full; coalescing dropped event reason=%s guard=%s",
                dropped.reason,
                dropped.guard,
            )

        self._queue.append(event)
        self._queued_count += 1
        self._pending_event.set()

    async def _run(self) -> None:
        while True:
            batch = await self._collect_batch()
            flush_attempted = False
            if batch:
                await self._flush_batch(batch)
                flush_attempted = True
            elif self._overflow_aggregates or self._pending_envelopes:
                await self._flush_batch([])
                flush_attempted = True

            if self._stop_event.is_set() and self._queued_count == 0:
                if not self._overflow_aggregates and not self._pending_envelopes:
                    return
                if flush_attempted:
                    pending_events = pending_event_count(
                        pending_envelopes=self._pending_envelopes,
                        overflow_aggregates=self._overflow_aggregates,
                    )
                    logger.warning(
                        "Guardian guard telemetry shutdown retained unsent pending envelopes: %d events",
                        pending_events,
                    )
                    self._persist_pending_envelopes()
                    return

    async def _collect_batch(self) -> list[MemoryGuardianGuardTelemetryEvent]:
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

    def _pop_next_event(self) -> MemoryGuardianGuardTelemetryEvent | None:
        if not self._queue:
            self._pending_event.clear()
            return None
        event = self._queue.popleft()
        self._queued_count -= 1
        if self._queued_count == 0:
            self._pending_event.clear()
        return event

    def _persist_pending_envelopes(self) -> None:
        persisted = self._pending_store.persist(list(self._pending_envelopes))
        if not persisted:
            logger.warning(
                "Guardian guard telemetry pending envelopes not persisted; will keep in-memory queue only (envelopes=%d)",
                len(self._pending_envelopes),
            )

    async def _flush_batch(self, batch: list[MemoryGuardianGuardTelemetryEvent]) -> None:
        if self._client is None:
            if batch:
                merge_aggregates(self._overflow_aggregates, {event: 1 for event in batch})
            self._pending_event.set()
            self._persist_pending_envelopes()
            return

        await flush_guardian_guard_telemetry_envelopes(
            client=self._client,
            config=self._config,
            pending_store=self._pending_store,
            pending_envelopes=self._pending_envelopes,
            overflow_aggregates=self._overflow_aggregates,
            pending_event=self._pending_event,
            batch=batch,
        )


_dispatcher: MemoryGuardianGuardTelemetryDispatcher | None = None


async def start_memory_guardian_guard_telemetry_dispatcher() -> None:
    """Start the shared guardian guard telemetry dispatcher."""
    global _dispatcher
    if _dispatcher is not None:
        return

    config = MemoryGuardianGuardTelemetryConfig.from_settings()
    if config is None:
        return

    dispatcher = MemoryGuardianGuardTelemetryDispatcher(config)
    await dispatcher.start()
    _dispatcher = dispatcher


async def stop_memory_guardian_guard_telemetry_dispatcher() -> None:
    """Stop the shared guardian guard telemetry dispatcher."""
    global _dispatcher
    if _dispatcher is None:
        return
    await _dispatcher.stop()
    _dispatcher = None


def enqueue_memory_guardian_guard_telemetry(
    *,
    reason: str,
    guard: str,
    frequency_tier: str,
    quiet_window_enabled: bool,
) -> None:
    """Enqueue one guard-unavailable telemetry event if dispatcher is active."""
    if _dispatcher is None:
        return
    normalized_reason = normalize_governed_label(reason, allowed=_ALLOWED_REASONS)
    normalized_guard = normalize_governed_label(guard, allowed=_ALLOWED_GUARDS)
    normalized_tier = normalize_governed_label(frequency_tier, allowed=_ALLOWED_FREQUENCY_TIERS)
    _dispatcher.enqueue(
        MemoryGuardianGuardTelemetryEvent(
            reason=normalized_reason,
            guard=normalized_guard,
            frequency_tier=normalized_tier,
            quiet_window_enabled=bool(quiet_window_enabled),
        )
    )


__all__ = [
    "MemoryGuardianGuardTelemetryConfig",
    "MemoryGuardianGuardTelemetryDispatcher",
    "MemoryGuardianGuardTelemetryEvent",
    "enqueue_memory_guardian_guard_telemetry",
    "start_memory_guardian_guard_telemetry_dispatcher",
    "stop_memory_guardian_guard_telemetry_dispatcher",
]
