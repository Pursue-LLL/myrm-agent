"""@input: httpx.AsyncClient + MemoryGuardianGuardTelemetryConfig + pending envelope queues
@output: envelope aggregation helpers + flush_guardian_guard_telemetry_envelopes()
@pos: HTTP transport layer for guardian guard-unavailable telemetry envelopes.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.schemas.control_plane import (
    MemoryGuardianGuardBatchPayload,
    MemoryGuardianGuardTelemetryAggregate,
    MemoryGuardianGuardTelemetryEnvelope,
)
from app.services.agent.memory_guardian_guard_telemetry.contract import (
    MemoryGuardianGuardTelemetryConfig,
    MemoryGuardianGuardTelemetryEvent,
)
from app.services.agent.memory_guardian_guard_telemetry.pending_store import (
    MemoryGuardianGuardPendingStore,
)

logger = logging.getLogger(__name__)

_ENDPOINT_PATH: str = "/api/telemetry/memory-guardian-guard/batch"
_TELEMETRY_SUBJECT_HEADER: str = "X-Telemetry-Subject"


def aggregate_batch_events(
    batch: list[MemoryGuardianGuardTelemetryEvent],
) -> dict[MemoryGuardianGuardTelemetryEvent, int]:
    aggregates: dict[MemoryGuardianGuardTelemetryEvent, int] = {}
    for event in batch:
        aggregates[event] = aggregates.get(event, 0) + 1
    return aggregates


def merge_aggregates(
    target: dict[MemoryGuardianGuardTelemetryEvent, int],
    incoming: dict[MemoryGuardianGuardTelemetryEvent, int],
) -> None:
    for event, count in incoming.items():
        if count <= 0:
            continue
        target[event] = target.get(event, 0) + count


def build_envelope(
    *,
    config: MemoryGuardianGuardTelemetryConfig,
    aggregates: dict[MemoryGuardianGuardTelemetryEvent, int],
) -> MemoryGuardianGuardTelemetryEnvelope:
    return MemoryGuardianGuardTelemetryEnvelope(
        telemetry_subject=config.telemetry_subject,
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


def drain_pending_envelopes(
    *,
    config: MemoryGuardianGuardTelemetryConfig,
    pending_envelopes: deque[MemoryGuardianGuardTelemetryEnvelope],
    overflow_aggregates: dict[MemoryGuardianGuardTelemetryEvent, int],
    batch: list[MemoryGuardianGuardTelemetryEvent],
) -> list[MemoryGuardianGuardTelemetryEnvelope]:
    envelopes = list(pending_envelopes)
    pending_envelopes.clear()
    aggregates = dict(overflow_aggregates)
    overflow_aggregates.clear()
    merge_aggregates(aggregates, aggregate_batch_events(batch))
    if aggregates:
        envelopes.append(build_envelope(config=config, aggregates=aggregates))
    return envelopes


def pending_event_count(
    *,
    pending_envelopes: deque[MemoryGuardianGuardTelemetryEnvelope],
    overflow_aggregates: dict[MemoryGuardianGuardTelemetryEvent, int],
) -> int:
    envelope_pending = sum(
        aggregate.count for envelope in pending_envelopes for aggregate in envelope.aggregates
    )
    aggregate_pending = sum(overflow_aggregates.values())
    return envelope_pending + aggregate_pending


async def flush_guardian_guard_telemetry_envelopes(
    *,
    client: httpx.AsyncClient,
    config: MemoryGuardianGuardTelemetryConfig,
    pending_store: MemoryGuardianGuardPendingStore,
    pending_envelopes: deque[MemoryGuardianGuardTelemetryEnvelope],
    overflow_aggregates: dict[MemoryGuardianGuardTelemetryEvent, int],
    pending_event: asyncio.Event,
    batch: list[MemoryGuardianGuardTelemetryEvent],
) -> None:
    envelopes = drain_pending_envelopes(
        config=config,
        pending_envelopes=pending_envelopes,
        overflow_aggregates=overflow_aggregates,
        batch=batch,
    )
    if not envelopes:
        return

    endpoint = f"{config.control_plane_url}{_ENDPOINT_PATH}"
    headers = {
        "X-Telemetry-Token": config.telemetry_token,
        _TELEMETRY_SUBJECT_HEADER: config.telemetry_subject,
    }
    payload = MemoryGuardianGuardBatchPayload(events=envelopes).model_dump()

    for attempt in range(2):
        try:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            persisted = pending_store.persist(list(pending_envelopes))
            if not persisted:
                logger.warning(
                    "Guardian guard telemetry pending envelopes not persisted after flush (envelopes=%d)",
                    len(pending_envelopes),
                )
            return
        except httpx.HTTPError as exc:
            if attempt == 1:
                for envelope in reversed(envelopes):
                    pending_envelopes.appendleft(envelope)
                pending_event.set()
                persisted = pending_store.persist(list(pending_envelopes))
                if not persisted:
                    logger.warning(
                        "Guardian guard telemetry pending envelopes not persisted after flush failure (envelopes=%d)",
                        len(pending_envelopes),
                    )
                logger.warning(
                    "Failed to flush guardian guard telemetry to %s (events=%d pending=%d): %s",
                    endpoint,
                    sum(aggregate.count for envelope in envelopes for aggregate in envelope.aggregates),
                    pending_event_count(
                        pending_envelopes=pending_envelopes,
                        overflow_aggregates=overflow_aggregates,
                    ),
                    exc,
                )
                return
            await asyncio.sleep(0.2)
