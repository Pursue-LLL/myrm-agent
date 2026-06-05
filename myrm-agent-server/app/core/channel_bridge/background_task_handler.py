"""ChannelBackgroundTaskHandler — business-layer handler for /background slash commands.

Spawns independent background agent sessions via ChannelAgentExecutor,
manages their lifecycle in memory, and pushes completion notifications
back to the originating channel and WebUI EventBus.

[INPUT]
- app.channels.types::InboundMessage, OutboundMessage (POS: Channel message types)
- app.channels.protocols.background_task (POS: Background task handler protocol)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: Cancellation token)
- myrm_agent_harness.utils.runtime.steering::SteeringToken (POS: Runtime steering injection)
- app.core.channel_bridge.agent_executor::ChannelAgentExecutor (POS: Channel agent execution pipeline)
- app.services.event.app_event_bus::get_event_bus, AppEvent, AppEventType (POS: WebUI SSE event bus)

[OUTPUT]
- ChannelBackgroundTaskHandler: BackgroundTaskHandler protocol implementation for channel background tasks

[POS]
Business-layer adapter connecting /background (/btw /bg) slash commands to
ChannelAgentExecutor. Each background task runs as an isolated agent session
with full tool access and streaming support, without interfering with the
user's active conversation.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.protocols.background_task import (
    BackgroundTaskInfo,
)
from app.channels.types import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TASKS = 5
TASK_TIMEOUT_SECONDS = 600.0


@dataclass
class _RunningTask:
    """In-memory record of a running background task."""

    task_id: str
    prompt: str
    channel: str
    chat_id: str
    user_id: str
    thread_id: str | None
    asyncio_task: asyncio.Task[str] | None = None
    cancel_token: CancellationToken | None = None
    steering_token: SteeringToken | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status: str = "running"
    result: str | None = None


class ChannelBackgroundTaskHandler:
    """BackgroundTaskHandler implementation for channel-based background tasks.

    Manages the lifecycle of background tasks spawned via /btw commands.
    Tasks are executed as independent agent runs that don't interfere with
    the user's current conversation.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, _RunningTask] = {}

    async def spawn_background(
        self,
        msg: InboundMessage,
        prompt: str,
    ) -> str:
        """Spawn a new background task."""
        self.cleanup_expired()

        running_count = sum(1 for t in self._tasks.values() if t.status == "running")
        if running_count >= MAX_CONCURRENT_TASKS:
            raise RuntimeError(
                f"Maximum concurrent background tasks reached ({MAX_CONCURRENT_TASKS}). "
                "Please wait for existing tasks to complete or cancel one."
            )

        task_id = f"bg_{uuid.uuid4().hex[:8]}"
        chat_id = msg.chat_id or msg.sender_id

        record = _RunningTask(
            task_id=task_id,
            prompt=prompt,
            channel=msg.channel,
            chat_id=chat_id,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
        )
        self._tasks[task_id] = record

        asyncio_task = asyncio.create_task(
            self._execute_with_timeout(record),
            name=f"background-task-{task_id}",
        )
        record.asyncio_task = asyncio_task
        asyncio_task.add_done_callback(lambda _t: self._on_task_done(task_id))

        logger.info(
            "Background task %s spawned for %s/%s: %s",
            task_id,
            msg.channel,
            chat_id,
            prompt[:80],
        )
        return task_id

    async def cancel_background(
        self,
        msg: InboundMessage,
        task_id: str,
    ) -> bool:
        """Cancel a running background task."""
        record = self._tasks.get(task_id)
        if not record or record.status != "running":
            return False

        if record.cancel_token:
            record.cancel_token.cancel("user_cancelled")

        if record.asyncio_task and not record.asyncio_task.done():
            record.asyncio_task.cancel()

        record.status = "cancelled"
        record.completed_at = time.time()
        logger.info("Background task %s cancelled", task_id)
        return True

    async def list_background(
        self,
        msg: InboundMessage,
    ) -> list[BackgroundTaskInfo]:
        """List all background tasks for the current user."""
        user_id = msg.user_id or msg.sender_id
        results: list[BackgroundTaskInfo] = []

        for record in self._tasks.values():
            if record.user_id != user_id and record.chat_id != (msg.chat_id or msg.sender_id):
                continue
            results.append(
                BackgroundTaskInfo(
                    task_id=record.task_id,
                    prompt=record.prompt,
                    status=record.status,
                    created_at=record.created_at,
                    completed_at=record.completed_at,
                    result_preview=record.result[:100] if record.result else None,
                )
            )

        return results

    async def steer_background(
        self,
        msg: InboundMessage,
        task_id: str,
        instruction: str,
    ) -> bool:
        """Inject a steering instruction into a running background task."""
        record = self._tasks.get(task_id)
        if not record or record.status != "running":
            return False

        if record.steering_token:
            record.steering_token.steer(instruction)
            return True

        return False

    async def _execute_with_timeout(self, record: _RunningTask) -> str:
        """Wrap _execute_background with a timeout guard."""
        try:
            return await asyncio.wait_for(
                self._execute_background(record),
                timeout=TASK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            record.status = "failed"
            record.result = f"Task timed out after {int(TASK_TIMEOUT_SECONDS)}s"
            record.completed_at = time.time()
            logger.warning("Background task %s timed out", record.task_id)
            await self._push_error(record, record.result)
            return record.result

    async def _execute_background(self, record: _RunningTask) -> str:
        """Execute the background task as an independent agent run.

        Uses the same ChannelAgentExecutor pipeline but in an isolated context,
        consuming the full stream to collect the final response.
        """
        from app.core.channel_bridge.agent_executor import ChannelAgentExecutor

        try:
            executor = ChannelAgentExecutor()
            cancel_token = CancellationToken()
            steering_token = SteeringToken()
            record.cancel_token = cancel_token
            record.steering_token = steering_token

            synthetic_msg = InboundMessage(
                channel=record.channel,
                sender_id=record.chat_id,
                chat_id=f"bg_{record.task_id}",
                content=record.prompt,
                user_id=record.user_id,
                metadata={"background_task_id": record.task_id},
            )

            result_parts: list[str] = []
            async for event in executor.execute_stream(
                synthetic_msg,
                user_id=record.user_id,
                cancel_token=cancel_token,
                steering_token=steering_token,
            ):
                if isinstance(event, OutboundMessage) and event.content:
                    result_parts.append(event.content)

            result = "\n".join(result_parts) if result_parts else "Task completed (no output)"
            record.status = "completed"
            record.result = result
            record.completed_at = time.time()

            await self._push_result(record)
            self._emit_event(record)
            return result

        except asyncio.CancelledError:
            record.status = "cancelled"
            record.completed_at = time.time()
            raise
        except Exception as exc:
            logger.error("Background task %s failed: %s", record.task_id, exc)
            record.status = "failed"
            record.result = f"Error: {exc}"
            record.completed_at = time.time()

            await self._push_error(record, str(exc))
            self._emit_event(record)
            return f"Error: {exc}"

    async def _push_result(self, record: _RunningTask) -> None:
        """Push background task result back to the originating channel."""
        from app.core.channel_bridge import channel_gateway

        bus = channel_gateway.bus

        result_preview = record.result or ""
        if len(result_preview) > 2000:
            result_preview = result_preview[:2000] + "\n\n...(truncated)"

        content = f"**Background task completed** `{record.task_id}`\n_Task: {record.prompt[:100]}_\n\n{result_preview}"

        reply = OutboundMessage(
            channel=record.channel,
            recipient_id=record.chat_id,
            content=content,
            user_id=record.user_id,
            thread_id=record.thread_id,
        )
        await bus.publish_outbound(reply)

    async def _push_error(self, record: _RunningTask, error: str) -> None:
        """Push background task error notification."""
        from app.core.channel_bridge import channel_gateway

        bus = channel_gateway.bus

        content = f"**Background task failed** `{record.task_id}`\n_Task: {record.prompt[:100]}_\n\nError: {error}"

        reply = OutboundMessage(
            channel=record.channel,
            recipient_id=record.chat_id,
            content=content,
            user_id=record.user_id,
            thread_id=record.thread_id,
        )
        await bus.publish_outbound(reply)

    def _emit_event(self, record: _RunningTask) -> None:
        """Emit SSE event to WebUI EventBus for real-time frontend updates."""
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        event_bus = get_event_bus()
        event_bus.publish(
            AppEvent(
                event_type=AppEventType.BACKGROUND_TASK_DONE,
                data={
                    "task_id": record.task_id,
                    "status": record.status,
                    "prompt": record.prompt[:100],
                    "result_preview": record.result[:200] if record.result else None,
                },
            )
        )

    def _on_task_done(self, task_id: str) -> None:
        """Cleanup callback when a background asyncio task completes."""
        record = self._tasks.get(task_id)
        if record and record.status == "running":
            record.status = "completed"
            record.completed_at = time.time()

    def cleanup_expired(self, max_age_seconds: float = 3600.0) -> int:
        """Remove completed tasks older than max_age_seconds. Returns count removed."""
        now = time.time()
        expired = [
            tid
            for tid, r in self._tasks.items()
            if r.status != "running" and r.completed_at and (now - r.completed_at) > max_age_seconds
        ]
        for tid in expired:
            del self._tasks[tid]
        return len(expired)
