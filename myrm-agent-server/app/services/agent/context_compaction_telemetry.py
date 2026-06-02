"""@input: httpx, settings.control_plane/context_compaction_telemetry, harness TaskMetrics
@output: ContextCompactionTelemetryDispatcher, enqueue/start/stop helpers
@pos: Server-side context compaction telemetry batch dispatch to Control Plane ([S] sandbox only).
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import QueueEmpty
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from myrm_agent_harness.agent.context_management.tracking.task_metrics import get_task_metrics

from app.config.settings import settings
from app.schemas.control_plane import (
    ContextCompactionSnapshot,
    ContextCompactionTelemetryEnvelope,
)

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS: float = 5.0
_ENDPOINT_PATH: str = "/api/telemetry/context-compaction/batch"
_DEFAULT_BATCH_SIZE: int = 16
_DEFAULT_FLUSH_INTERVAL_SECONDS: float = 2.0
_DEFAULT_QUEUE_SIZE: int = 256
_TELEMETRY_SUBJECT_HEADER: str = "X-Telemetry-Subject"


@dataclass(frozen=True)
class ContextCompactionTelemetryConfig:
    """Validated runtime config for telemetry dispatch."""

    control_plane_url: str
    telemetry_token: str
    telemetry_subject: str
    batch_size: int
    flush_interval_seconds: float
    queue_size: int

    @classmethod
    def from_settings(cls) -> ContextCompactionTelemetryConfig | None:
        cp = settings.control_plane
        telemetry = settings.context_compaction_telemetry
        control_plane_url = cp.url.strip()
        telemetry_token = cp.telemetry_token.get_secret_value()
        telemetry_subject = cp.telemetry_subject.strip()

        present_count = sum(
            bool(value) for value in (control_plane_url, telemetry_token, telemetry_subject)
        )
        if present_count == 0:
            logger.info("Context compaction telemetry disabled: no control plane telemetry configured")
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
                "Context compaction telemetry disabled: missing required settings: %s",
                ", ".join(missing),
            )
            return None

        batch_size = telemetry.batch_size if telemetry.batch_size > 0 else _DEFAULT_BATCH_SIZE
        flush_interval = (
            telemetry.flush_interval_seconds
            if telemetry.flush_interval_seconds > 0
            else _DEFAULT_FLUSH_INTERVAL_SECONDS
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


class ContextCompactionTelemetryDispatcher:
    """Bounded in-process dispatcher with batching and graceful shutdown."""

    def __init__(self, config: ContextCompactionTelemetryConfig) -> None:
        self._config = config
        self._queue: asyncio.Queue[ContextCompactionTelemetryEnvelope] = asyncio.Queue(maxsize=config.queue_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._stop_event.clear()
        self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS)
        self._worker_task = asyncio.create_task(self._run(), name="context-compaction-telemetry")
        logger.info(
            "Context compaction telemetry dispatcher started: batch=%d interval=%.2fs queue=%d",
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
        logger.info("Context compaction telemetry dispatcher stopped")

    def enqueue(self, chat_id: str | None) -> None:
        envelope = _build_context_compaction_envelope(chat_id, self._config)
        if envelope is None:
            return

        if self._queue.full():
            try:
                dropped = self._queue.get_nowait()
            except QueueEmpty:
                dropped = None
            if dropped is not None:
                logger.warning(
                    "Context compaction telemetry queue full; dropping oldest snapshot for chat %s",
                    dropped.chat_id,
                )

        self._queue.put_nowait(envelope)

    async def _run(self) -> None:
        while True:
            batch = await self._collect_batch()
            if batch:
                await self._flush_batch(batch)

            if self._stop_event.is_set() and self._queue.empty():
                return

    async def _collect_batch(self) -> list[ContextCompactionTelemetryEnvelope]:
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

    async def _flush_batch(self, batch: list[ContextCompactionTelemetryEnvelope]) -> None:
        if self._client is None:
            return

        endpoint = f"{self._config.control_plane_url}{_ENDPOINT_PATH}"
        headers = {
            "X-Telemetry-Token": self._config.telemetry_token,
            _TELEMETRY_SUBJECT_HEADER: self._config.telemetry_subject,
        }
        payload = {"events": [item.model_dump() for item in batch]}

        for attempt in range(2):
            try:
                response = await self._client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                return
            except httpx.HTTPError as exc:
                if attempt == 1:
                    logger.warning(
                        "Failed to flush %d context compaction telemetry items to %s: %s",
                        len(batch),
                        endpoint,
                        exc,
                    )
                    return
                await asyncio.sleep(0.2)


_dispatcher: ContextCompactionTelemetryDispatcher | None = None


async def start_context_compaction_telemetry_dispatcher() -> None:
    """Start the shared telemetry dispatcher when config is complete."""
    global _dispatcher

    if _dispatcher is not None:
        return

    config = ContextCompactionTelemetryConfig.from_settings()
    if config is None:
        return

    dispatcher = ContextCompactionTelemetryDispatcher(config)
    await dispatcher.start()
    _dispatcher = dispatcher


async def stop_context_compaction_telemetry_dispatcher() -> None:
    """Stop the shared telemetry dispatcher and flush pending data."""
    global _dispatcher

    if _dispatcher is None:
        return
    await _dispatcher.stop()
    _dispatcher = None


def enqueue_context_compaction_telemetry(chat_id: str | None) -> None:
    """Enqueue a compaction telemetry snapshot if the dispatcher is active."""
    if _dispatcher is None:
        return
    _dispatcher.enqueue(chat_id)


def _build_context_compaction_envelope(
    chat_id: str | None,
    config: ContextCompactionTelemetryConfig,
) -> ContextCompactionTelemetryEnvelope | None:
    """Build a detached telemetry envelope from the in-memory TaskMetrics snapshot."""
    if not chat_id:
        return None

    metrics = get_task_metrics(chat_id)
    if metrics is None or metrics.compression_count <= 0:
        return None

    return ContextCompactionTelemetryEnvelope(
        telemetry_subject=config.telemetry_subject,
        chat_id=chat_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        snapshot=ContextCompactionSnapshot.from_mapping(metrics.to_dict()),
    )


__all__ = [
    "ContextCompactionTelemetryConfig",
    "ContextCompactionTelemetryDispatcher",
    "ContextCompactionTelemetryEnvelope",
    "enqueue_context_compaction_telemetry",
    "start_context_compaction_telemetry_dispatcher",
    "stop_context_compaction_telemetry_dispatcher",
]
