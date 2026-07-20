"""@input: httpx.AsyncClient + MemoryBriefStatusTelemetryConfig + batch events + MemoryBriefStatusDroppedStore
@output: flush_memory_brief_status_batch() — POST Control Plane + ack dropped snapshot on success
@pos: HTTP transport layer for memory brief status telemetry envelopes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.schemas.control_plane import (
    MemoryBriefStatusBatchPayload,
    MemoryBriefStatusTelemetryAggregate,
    MemoryBriefStatusTelemetryEnvelope,
)
from app.services.agent.memory_brief_telemetry import metrics as _metrics
from app.services.agent.memory_brief_telemetry.contract import (
    MemoryBriefStatusTelemetryConfig,
    MemoryBriefStatusTelemetryEvent,
)
from app.services.agent.memory_brief_telemetry.dropped_store import (
    MemoryBriefStatusDroppedStore,
    serialize_dropped_aggregates,
)

logger = logging.getLogger(__name__)

_ENDPOINT_PATH: str = "/api/telemetry/memory-brief-status/batch"
_TELEMETRY_SUBJECT_HEADER: str = "X-Telemetry-Subject"


async def flush_memory_brief_status_batch(
    *,
    client: httpx.AsyncClient,
    config: MemoryBriefStatusTelemetryConfig,
    batch: list[MemoryBriefStatusTelemetryEvent],
    dropped_store: MemoryBriefStatusDroppedStore,
) -> None:
    endpoint = f"{config.control_plane_url}{_ENDPOINT_PATH}"
    headers = {
        "X-Telemetry-Token": config.telemetry_token,
        _TELEMETRY_SUBJECT_HEADER: config.telemetry_subject,
    }

    aggregates: dict[MemoryBriefStatusTelemetryEvent, int] = {}
    for event in batch:
        aggregates[event] = aggregates.get(event, 0) + 1
    dropped_snapshot = dropped_store.snapshot()
    dropped_event_count = sum(dropped_snapshot.values())

    envelope = MemoryBriefStatusTelemetryEnvelope(
        telemetry_subject=config.telemetry_subject,
        envelope_id=f"mbs-{uuid4().hex}",
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
        dropped_aggregates=serialize_dropped_aggregates(dropped_snapshot),
    )
    payload = MemoryBriefStatusBatchPayload(events=[envelope]).model_dump()

    for attempt in range(2):
        try:
            if _metrics.MEMORY_STATUS_FLUSH_ATTEMPTS is not None:
                _metrics.MEMORY_STATUS_FLUSH_ATTEMPTS.labels(
                    telemetry_subject=config.telemetry_subject
                ).inc()
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            dropped_store.ack(dropped_snapshot)
            return
        except httpx.HTTPError as exc:
            if attempt == 1:
                if _metrics.MEMORY_STATUS_FLUSH_HTTP_ERRORS is not None:
                    _metrics.MEMORY_STATUS_FLUSH_HTTP_ERRORS.labels(
                        telemetry_subject=config.telemetry_subject
                    ).inc()
                logger.warning(
                    "Failed to flush memory brief status telemetry to %s (status_events=%d dropped_events=%d): %s",
                    endpoint,
                    len(batch),
                    dropped_event_count,
                    exc,
                )
                return
            await asyncio.sleep(0.2)
