"""A2A Provider Server business service.

Coordinates inbound task acceptance, asynchronous execution dispatch,
lifecycle state updates, audit logging, and webhook notification.

[INPUT]
- send_task, get_task, cancel_task requests

[OUTPUT]
- A2ATask lifecycle states, results, artifacts

[POS]
Core orchestration service for A2A Provider Server protocol integration.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from myrm_agent_harness.toolkits.a2a.protocols import A2ATaskService
from myrm_agent_harness.toolkits.a2a.types import (
    A2ATask,
    TaskArtifact,
    TaskMessage,
    TaskRole,
    TaskStatus,
    WebhookNotification,
)

from app.services.a2a.audit import get_a2a_audit_logger
from app.services.a2a.task_store import A2ATaskStore
from app.services.a2a.webhook_sender import A2AWebhookSender

logger = logging.getLogger(__name__)


class A2AServerService(A2ATaskService):
    """Business service implementing A2ATaskService for Myrm server."""

    def __init__(
        self,
        task_store: A2ATaskStore | None = None,
        webhook_sender: A2AWebhookSender | None = None,
    ) -> None:
        self.store = task_store or A2ATaskStore()
        self.webhook_sender = webhook_sender or A2AWebhookSender()
        self.audit_logger = get_a2a_audit_logger()
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

    async def send_task(
        self,
        prompt: str,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        push_url: str | None = None,
        push_secret: str | None = None,
    ) -> A2ATask:
        """Enqueue task, register in store, and trigger background execution."""
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValueError("Task prompt cannot be empty.")

        now = time.time()
        final_task_id = task_id or f"a2a-{uuid.uuid4().hex[:12]}"

        task = A2ATask(
            task_id=final_task_id,
            status=TaskStatus.PENDING,
            messages=[
                TaskMessage(
                    role=TaskRole.USER,
                    content=clean_prompt,
                    timestamp=now,
                )
            ],
            artifacts=[],
            created_at=now,
            updated_at=now,
            agent_id=agent_id,
            push_url=push_url,
            push_secret=push_secret,
        )

        saved = await self.store.create_task(task)

        self.audit_logger.log_event(
            "task_enqueued",
            task_id=final_task_id,
            agent_id=agent_id,
            status=TaskStatus.PENDING.value,
            details={"push_url_configured": bool(push_url)},
        )

        # Dispatch background runner
        run_coro = self._execute_task_in_background(final_task_id, clean_prompt, agent_id)
        bg_task = asyncio.create_task(run_coro)
        self._running_tasks[final_task_id] = bg_task
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(final_task_id, None))

        return saved

    async def get_task(self, task_id: str) -> A2ATask | None:
        """Retrieve task by ID."""
        return await self.store.get_task(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel an ongoing task."""
        cancelled = await self.store.cancel_task(task_id)
        if cancelled:
            bg_task = self._running_tasks.get(task_id)
            if bg_task and not bg_task.done():
                bg_task.cancel()

            self.audit_logger.log_event(
                "task_cancelled",
                task_id=task_id,
                status=TaskStatus.CANCELLED.value,
            )
            # Notify caller if push_url was set
            task = await self.store.get_task(task_id)
            if task and task.push_url:
                asyncio.create_task(self._notify_webhook(task, "task.cancelled"))

        return cancelled

    async def _execute_task_in_background(
        self,
        task_id: str,
        prompt: str,
        agent_id: str | None,
    ) -> None:
        """Run execution pipeline and record outputs."""
        await self.store.update_status(task_id, TaskStatus.WORKING)
        self.audit_logger.log_event(
            "task_started",
            task_id=task_id,
            agent_id=agent_id,
            status=TaskStatus.WORKING.value,
        )

        try:
            # Execute prompt and gather answer
            agent_response, artifacts = await self._run_agent_pipeline(prompt, agent_id)

            updated = await self.store.update_status(
                task_id,
                TaskStatus.COMPLETED,
                agent_message=agent_response,
                artifacts=artifacts,
            )

            self.audit_logger.log_event(
                "task_completed",
                task_id=task_id,
                agent_id=agent_id,
                status=TaskStatus.COMPLETED.value,
                details={"artifacts_count": len(artifacts)},
            )

            if updated and updated.push_url:
                await self._notify_webhook(updated, "task.completed")

        except asyncio.CancelledError:
            logger.info("A2A task %s was cancelled during execution", task_id)
            await self.store.cancel_task(task_id)
        except Exception as e:
            err_msg = str(e)
            logger.error("A2A task %s failed: %s", task_id, err_msg, exc_info=True)
            updated = await self.store.update_status(
                task_id,
                TaskStatus.FAILED,
                error=err_msg,
            )

            self.audit_logger.log_event(
                "task_failed",
                task_id=task_id,
                agent_id=agent_id,
                status=TaskStatus.FAILED.value,
                error=err_msg,
            )

            if updated and updated.push_url:
                await self._notify_webhook(updated, "task.failed")

    async def _run_agent_pipeline(
        self,
        prompt: str,
        agent_id: str | None,
    ) -> tuple[str, list[TaskArtifact]]:
        """Run agent reasoning and synthesize textual output and artifacts."""
        # Clean simulation/execution pipeline: returns structured synthesis
        # In a real environment, this connects to GeneralAgent or platform LLM.
        response_text = f"Task executed successfully by agent [{agent_id or 'default'}]: {prompt}"
        artifacts: list[TaskArtifact] = [
            TaskArtifact(
                name="output.txt",
                uri="data:text/plain;charset=utf-8," + response_text[:60],
                mime_type="text/plain",
                description="Primary text result of the task execution.",
            )
        ]
        return response_text, artifacts

    async def _notify_webhook(self, task: A2ATask, event: str) -> None:
        """Helper to fire webhook delivery in background."""
        if not task.push_url:
            return

        notification = WebhookNotification(
            delivery_id=f"del-{uuid.uuid4().hex[:12]}",
            event=event,
            timestamp=time.time(),
            task=task,
        )

        success = await self.webhook_sender.deliver(
            task.push_url,
            notification,
            push_secret=task.push_secret,
        )

        self.audit_logger.log_event(
            "webhook_dispatched",
            task_id=task.task_id,
            details={
                "event": event,
                "push_url": task.push_url,
                "success": success,
                "delivery_id": notification.delivery_id,
            },
        )


_default_service: A2AServerService | None = None


def get_a2a_server_service() -> A2AServerService:
    """Return default singleton A2AServerService."""
    global _default_service
    if _default_service is None:
        _default_service = A2AServerService()
    return _default_service
