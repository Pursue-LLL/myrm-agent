"""SSE bridge translating harness failover/recovery events into stream chunks.

[INPUT]
- myrm_agent_harness.toolkits.llms.fallback (POS: FailoverEmitter Protocol, FailoverEvent, RecoveryEvent)
- app.schemas.streaming (POS: SSEEnvelope serializer)
- app.services.agent.streaming_support.stream_collector (POS: StreamContentCollector for persistence)

[OUTPUT]
- SSEFailoverEmitter: harness ↔ SSE adapter that converts FailoverEvent / RecoveryEvent
  into MODEL_FAILOVER / MODEL_RECOVERY chunks and exposes a drainable async queue.
- merge_stream_with_emitter: helper combining the main agent chunk iterator with the
  emitter queue so failover notifications surface immediately, even mid-LLM-call.

[POS]
Server-side wiring layer for the harness ``FailoverEmitter`` contract. Surfaces
transport-level model failovers (HTTP 5xx, timeouts, rate-limit) as first-class
SSE events so users see in real time that their model auto-switched, instead of
silently degrading from a premium reasoning model to a cheaper backup.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Final

from myrm_agent_harness.toolkits.llms.fallback import FailoverEvent, RecoveryEvent

from app.schemas.streaming import SSEEnvelope
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

logger = logging.getLogger(__name__)

MODEL_FAILOVER_EVENT_TYPE: Final[str] = "model_failover"
MODEL_RECOVERY_EVENT_TYPE: Final[str] = "model_recovery"

_EMITTER_QUEUE_SENTINEL: Final[object] = object()


class SSEFailoverEmitter:
    """Bridges harness failover events to SSE chunks scoped to one stream session.

    Lifetime is tied to ``generate_cancellable_stream``: one emitter per
    streaming response. Concurrent emits from the same ``ManagedLLM`` are
    serialized through the internal ``asyncio.Queue`` so frontend ordering is
    preserved relative to the main agent chunk flow.
    """

    def __init__(self, message_id: str | None, collector: StreamContentCollector) -> None:
        self._message_id = message_id or ""
        self._collector = collector
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._closed = False

    @property
    def queue(self) -> asyncio.Queue[str]:
        """Return the queue stream consumers should drain."""
        return self._queue

    async def emit_failover(self, event: FailoverEvent) -> None:
        if self._closed:
            return

        payload = {
            "type": MODEL_FAILOVER_EVENT_TYPE,
            "messageId": self._message_id,
            "data": {
                "fromModel": event.from_model,
                "toModel": event.to_model,
                "reason": event.reason.value,
                "errorMessage": event.error_message,
                "cooldownMs": event.cooldown_ms,
                "attemptCount": event.attempt_count,
                "availableCandidates": list(event.available_candidates),
                "scenario": event.scenario,
            },
        }
        await self._publish(payload)

    async def emit_recovery(self, event: RecoveryEvent) -> None:
        if self._closed:
            return

        payload = {
            "type": MODEL_RECOVERY_EVENT_TYPE,
            "messageId": self._message_id,
            "data": {
                "model": event.model,
                "downtimeMs": event.downtime_ms,
                "probeCount": event.probe_count,
                "wasInCooldown": event.was_in_cooldown,
            },
        }
        await self._publish(payload)

    async def _publish(self, payload: dict[str, object]) -> None:
        try:
            sse_chunk = SSEEnvelope.from_any(payload).to_sse_chunk()
        except Exception:
            logger.exception("Failed to serialize failover/recovery event: %s", payload)
            return

        # Record into the collector so the persisted assistant message keeps a
        # historical trace of the auto-switch, mirroring how routing_decision
        # is recorded upstream.
        try:
            self._collector.feed_event(payload)
        except Exception:
            logger.exception("Collector rejected failover/recovery event: %s", payload)

        await self._queue.put(sse_chunk)

    def close(self) -> None:
        """Signal that no further events will be enqueued.

        Safe to call multiple times. Drains a sentinel so any in-flight
        ``merge_stream_with_emitter`` consumer can short-circuit cleanly.
        """
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(_EMITTER_QUEUE_SENTINEL)  # type: ignore[arg-type]
        except Exception:
            pass


async def merge_stream_with_emitter(
    main_stream: AsyncIterator[str],
    emitter: SSEFailoverEmitter,
) -> AsyncGenerator[str, None]:
    """Yield from ``main_stream`` while interleaving any chunks from ``emitter.queue``.

    Uses ``asyncio.wait(FIRST_COMPLETED)`` so a failover event surfaces the
    moment the manager raises it, even if the main agent generator is currently
    blocked awaiting the next LLM token. The main stream's completion drives
    termination; once it ends the queue is drained one last time then closed.
    """
    main_iter = main_stream.__aiter__()
    main_task: asyncio.Task[str] | None = asyncio.ensure_future(main_iter.__anext__())
    queue_task: asyncio.Task[object] = asyncio.ensure_future(emitter.queue.get())

    try:
        while main_task is not None:
            done, _pending = await asyncio.wait(
                {task for task in (main_task, queue_task) if task is not None},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if queue_task in done:
                try:
                    item = queue_task.result()
                except Exception:
                    logger.exception("Failover emitter queue task failed")
                    item = _EMITTER_QUEUE_SENTINEL
                if isinstance(item, str):
                    yield item
                queue_task = asyncio.ensure_future(emitter.queue.get())

            if main_task is not None and main_task in done:
                try:
                    chunk = main_task.result()
                except StopAsyncIteration:
                    main_task = None
                    break
                yield chunk
                main_task = asyncio.ensure_future(main_iter.__anext__())

        # Drain any failover events that arrived between the last yield and the
        # main iterator finishing. Non-blocking: only items already enqueued
        # are surfaced; we never wait for new ones because the producer has
        # been signalled to stop via ``emitter.close()``.
        emitter.close()
        while not emitter.queue.empty():
            try:
                pending = emitter.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(pending, str):
                yield pending
    finally:
        emitter.close()
        if queue_task is not None and not queue_task.done():
            queue_task.cancel()
            try:
                await queue_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
            except Exception:
                logger.debug("Queue task cleanup raised", exc_info=True)
        if main_task is not None and not main_task.done():
            main_task.cancel()
            try:
                await main_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
            except Exception:
                logger.debug("Main task cleanup raised", exc_info=True)
