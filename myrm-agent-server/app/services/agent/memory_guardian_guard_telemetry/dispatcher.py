"""@input: guard-unavailable labels + control-plane telemetry settings
@output: MemoryGuardianGuardTelemetryDispatcher + enqueue/start/stop helpers
@pos: Server-side aggregated guardian guard-unavailable telemetry batch dispatch ([S] sandbox only).
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from app.config.settings import settings
from app.schemas.control_plane import (
    MemoryGuardianGuardBatchPayload,
    MemoryGuardianGuardTelemetryAggregate,
    MemoryGuardianGuardTelemetryEnvelope,
)
from app.services.agent.memory_guardian_guard_telemetry.pending_store import (
    MemoryGuardianGuardPendingStore,
)

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS: float = 5.0
_ENDPOINT_PATH: str = "/api/telemetry/memory-guardian-guard/batch"
_DEFAULT_BATCH_SIZE: int = 24
_DEFAULT_FLUSH_INTERVAL_SECONDS: float = 3.0
_DEFAULT_QUEUE_SIZE: int = 256
_TELEMETRY_SUBJECT_HEADER: str = "X-Telemetry-Subject"
_LABEL_UNKNOWN: str = "unknown"
_LABEL_MAX_LENGTH: int = 64
_PENDING_STATE_FILENAME: str = "memory_guardian_guard_pending_envelopes.json"
_ALLOWED_REASONS: frozenset[str] = frozenset(
    {
        "active_session_guard_unavailable",
        "budget_guard_unavailable",
        "capacity_guard_unavailable",
    }
)
_ALLOWED_GUARDS: frozenset[str] = frozenset(
    {
        "active_session",
        "budget",
        "capacity",
    }
)
_ALLOWED_FREQUENCY_TIERS: frozenset[str] = frozenset(
    {
        "conservative",
        "balanced",
        "aggressive",
    }
)


def _normalize_governed_label(
    raw: str,
    *,
    allowed: frozenset[str],
) -> str:
    value = raw.strip().lower()
    if not value:
        return _LABEL_UNKNOWN
    if len(value) > _LABEL_MAX_LENGTH:
        return _LABEL_UNKNOWN
    if value not in allowed:
        return _LABEL_UNKNOWN
    return value


@dataclass(frozen=True)
class MemoryGuardianGuardTelemetryEvent:
    """Compact guard-unavailable labels used for aggregation and transport."""

    reason: str
    guard: str
    frequency_tier: str
    quiet_window_enabled: bool


@dataclass(frozen=True)
class MemoryGuardianGuardTelemetryConfig:
    """Validated runtime config for guardian guard telemetry dispatch."""

    control_plane_url: str
    telemetry_token: str
    telemetry_subject: str
    batch_size: int
    flush_interval_seconds: float
    queue_size: int
    pending_state_path: str = ""

    @classmethod
    def from_settings(cls) -> MemoryGuardianGuardTelemetryConfig | None:
        cp = settings.control_plane
        telemetry = settings.memory_guardian_guard_telemetry
        control_plane_url = cp.url.strip()
        telemetry_token = cp.telemetry_token.get_secret_value()
        telemetry_subject = cp.telemetry_subject.strip()

        present_count = sum(bool(value) for value in (control_plane_url, telemetry_token, telemetry_subject))
        if present_count == 0:
            logger.info("Guardian guard telemetry disabled: no control plane telemetry configured")
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
                "Guardian guard telemetry disabled: missing required settings: %s",
                ", ".join(missing),
            )
            return None

        batch_size = telemetry.batch_size if telemetry.batch_size > 0 else _DEFAULT_BATCH_SIZE
        flush_interval = (
            telemetry.flush_interval_seconds if telemetry.flush_interval_seconds > 0 else _DEFAULT_FLUSH_INTERVAL_SECONDS
        )
        queue_size = telemetry.queue_size if telemetry.queue_size > 0 else _DEFAULT_QUEUE_SIZE
        pending_state_path = str(
            Path(settings.database.state_dir).expanduser().resolve() / _PENDING_STATE_FILENAME
        )

        return cls(
            control_plane_url=control_plane_url.rstrip("/"),
            telemetry_token=telemetry_token,
            telemetry_subject=telemetry_subject,
            batch_size=batch_size,
            flush_interval_seconds=flush_interval,
            queue_size=queue_size,
            pending_state_path=pending_state_path,
        )


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
        self._pending_envelopes: deque[MemoryGuardianGuardTelemetryEnvelope] = deque(
            self._pending_store.load()
        )
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
            self._merge_aggregates({dropped: 1})
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
                    pending_events = self._pending_event_count()
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

    def _aggregate_batch_events(
        self,
        batch: list[MemoryGuardianGuardTelemetryEvent],
    ) -> dict[MemoryGuardianGuardTelemetryEvent, int]:
        aggregates: dict[MemoryGuardianGuardTelemetryEvent, int] = {}
        for event in batch:
            aggregates[event] = aggregates.get(event, 0) + 1
        return aggregates

    def _merge_aggregates(self, aggregates: dict[MemoryGuardianGuardTelemetryEvent, int]) -> None:
        for event, count in aggregates.items():
            if count <= 0:
                continue
            self._overflow_aggregates[event] = self._overflow_aggregates.get(event, 0) + count

    def _drain_pending_aggregates(
        self,
        batch: list[MemoryGuardianGuardTelemetryEvent],
    ) -> dict[MemoryGuardianGuardTelemetryEvent, int]:
        aggregates = dict(self._overflow_aggregates)
        self._overflow_aggregates.clear()
        for event, count in self._aggregate_batch_events(batch).items():
            aggregates[event] = aggregates.get(event, 0) + count
        return aggregates

    def _build_envelope(
        self,
        aggregates: dict[MemoryGuardianGuardTelemetryEvent, int],
    ) -> MemoryGuardianGuardTelemetryEnvelope:
        return MemoryGuardianGuardTelemetryEnvelope(
            telemetry_subject=self._config.telemetry_subject,
            envelope_id=f"mgg-{uuid4().hex}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            aggregates=[
                MemoryGuardianGuardTelemetryAggregate(
                    reason=event.reason,
                    guard=event.guard,
                    frequency_tier=event.frequency_tier,
                    quiet_window_enabled=event.quiet_window_enabled,
                    count=count,
                )
                for event, count in aggregates.items()
            ],
        )

    def _drain_pending_envelopes(
        self,
        batch: list[MemoryGuardianGuardTelemetryEvent],
    ) -> list[MemoryGuardianGuardTelemetryEnvelope]:
        envelopes = list(self._pending_envelopes)
        self._pending_envelopes.clear()
        aggregates = self._drain_pending_aggregates(batch)
        if aggregates:
            envelopes.append(self._build_envelope(aggregates))
        return envelopes

    def _requeue_pending_envelopes(
        self,
        envelopes: list[MemoryGuardianGuardTelemetryEnvelope],
    ) -> None:
        for envelope in reversed(envelopes):
            self._pending_envelopes.appendleft(envelope)
        self._pending_event.set()
        self._persist_pending_envelopes()

    def _persist_pending_envelopes(self) -> None:
        persisted = self._pending_store.persist(list(self._pending_envelopes))
        if not persisted:
            logger.warning(
                "Guardian guard telemetry pending envelopes not persisted; will keep in-memory queue only (envelopes=%d)",
                len(self._pending_envelopes),
            )

    def _pending_event_count(self) -> int:
        envelope_pending = sum(
            aggregate.count for envelope in self._pending_envelopes for aggregate in envelope.aggregates
        )
        aggregate_pending = sum(self._overflow_aggregates.values())
        return envelope_pending + aggregate_pending

    async def _flush_batch(self, batch: list[MemoryGuardianGuardTelemetryEvent]) -> None:
        envelopes = self._drain_pending_envelopes(batch)
        if not envelopes:
            return

        if self._client is None:
            self._requeue_pending_envelopes(envelopes)
            return

        endpoint = f"{self._config.control_plane_url}{_ENDPOINT_PATH}"
        headers = {
            "X-Telemetry-Token": self._config.telemetry_token,
            _TELEMETRY_SUBJECT_HEADER: self._config.telemetry_subject,
        }
        payload = MemoryGuardianGuardBatchPayload(events=envelopes).model_dump()

        for attempt in range(2):
            try:
                response = await self._client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                self._persist_pending_envelopes()
                return
            except httpx.HTTPError as exc:
                if attempt == 1:
                    self._requeue_pending_envelopes(envelopes)
                    logger.warning(
                        "Failed to flush guardian guard telemetry to %s (events=%d pending=%d): %s",
                        endpoint,
                        sum(aggregate.count for envelope in envelopes for aggregate in envelope.aggregates),
                        self._pending_event_count(),
                        exc,
                    )
                    return
                await asyncio.sleep(0.2)


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
    normalized_reason = _normalize_governed_label(reason, allowed=_ALLOWED_REASONS)
    normalized_guard = _normalize_governed_label(guard, allowed=_ALLOWED_GUARDS)
    normalized_tier = _normalize_governed_label(frequency_tier, allowed=_ALLOWED_FREQUENCY_TIERS)
    _dispatcher.enqueue(
        MemoryGuardianGuardTelemetryEvent(
            reason=normalized_reason,
            guard=normalized_guard,
            frequency_tier=normalized_tier,
            quiet_window_enabled=bool(quiet_window_enabled),
        )
    )
