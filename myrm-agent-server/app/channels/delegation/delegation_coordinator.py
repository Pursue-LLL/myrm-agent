"""Asynchronous delegation coordinator and in-flight steering pipeline.

Coordinates execution lifecycle of delegated tasks and bridges in-flight prompt
injections to running Agent sandboxes via SteeringToken.

[INPUT]
- .delegation_models::DelegationTask, DelegationStatus
- app.channels.routing.friendly_errors::friendly_error_message, is_error_reply (POS: member-safe failure wording and failed-turn flag)
- myrm_agent_harness.utils.runtime.steering::SteeringToken
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken

[OUTPUT]
- DelegationCoordinator: Central coordinator managing task state machines, steering, and the background execution lifecycle.

[POS]
Execution lifecycle and coordination engine for app/channels/delegation/.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.routing.friendly_errors import friendly_error_message, is_error_reply
from app.channels.types import OutboundMessage, StreamingText

from .delegation_delivery import build_delivery_message
from .delegation_models import DelegationStatus, DelegationTask

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.protocols.agent import AgentExecutor
    from app.channels.types import InboundMessage

logger = logging.getLogger("myrm.channels.delegation.coordinator")

_TERMINAL_STATUSES = (DelegationStatus.COMPLETED, DelegationStatus.FAILED, DelegationStatus.TIMED_OUT)


class DelegationCoordinator:
    """Coordinates task execution and in-flight prompt steering."""

    def __init__(self) -> None:
        self._tasks: dict[str, DelegationTask] = {}
        self._cancellation_tokens: dict[str, CancellationToken] = {}
        self._steering_tokens: dict[str, SteeringToken] = {}

    def register_task(self, task: DelegationTask) -> None:
        """Register a newly created delegated task."""
        self._tasks[task.task_id] = task
        self._cancellation_tokens[task.task_id] = CancellationToken()
        self._steering_tokens[task.task_id] = SteeringToken()
        logger.info("DelegationCoordinator: Registered task %s for user %s", task.task_id, task.origin_user_id)

    def get_task(self, task_id: str) -> DelegationTask | None:
        """Retrieve task by ID."""
        return self._tasks.get(task_id)

    def update_task_status(
        self,
        task_id: str,
        status: DelegationStatus,
        *,
        error_message: str = "",
    ) -> None:
        """Transition task lifecycle status."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = status
        now = time.time()
        if status == DelegationStatus.RUNNING and task.started_at is None:
            task.started_at = now
        elif status in _TERMINAL_STATUSES:
            task.completed_at = now

        if error_message:
            task.error_message = error_message

        logger.info("DelegationCoordinator: Task %s transitioned to %s", task_id, status.value)

    def inject_steering(self, task_id: str, content: str, sender_id: str) -> bool:
        """Inject in-flight instruction into a running task.

        Args:
            task_id: Target task ID.
            content: User follow-up text.
            sender_id: Inbound message sender ID.

        Returns:
            True if successfully injected, False if task is not running.
        """
        task = self._tasks.get(task_id)
        if not task or task.status != DelegationStatus.RUNNING:
            logger.warning(
                "DelegationCoordinator: Cannot steer task %s in state %s", task_id, task.status.value if task else "unknown"
            )
            return False

        steering_token = self._steering_tokens.get(task_id)
        if steering_token:
            steering_token.steer(content)
        logger.info("DelegationCoordinator: Injected in-flight steering to task %s by %s", task_id, sender_id)
        return True

    def find_active_task(self, channel: str, user_id: str) -> DelegationTask | None:
        """Find the currently active or running task for a user in a channel."""
        for task in self._tasks.values():
            if (
                task.origin_channel == channel
                and task.origin_user_id == user_id
                and task.status in (DelegationStatus.PENDING, DelegationStatus.RUNNING)
            ):
                return task
        return None

    def get_steering_token(self, task_id: str) -> SteeringToken | None:
        """Retrieve the steering token for a task."""
        return self._steering_tokens.get(task_id)

    def get_cancellation_token(self, task_id: str) -> CancellationToken | None:
        """Retrieve the cancellation token for a task."""
        return self._cancellation_tokens.get(task_id)

    def reap_stale_tasks(self, max_age_seconds: float = 7200.0) -> list[str]:
        """Reap tasks that have exceeded their timeout or run past max age.

        Returns:
            List of reaped task IDs.
        """
        now = time.time()
        reaped: list[str] = []
        for task_id, task in list(self._tasks.items()):
            if task.status in _TERMINAL_STATUSES:
                continue
            started = task.started_at or task.created_at
            timeout = task.timeout_seconds or max_age_seconds
            if now - started > timeout:
                self.update_task_status(task_id, DelegationStatus.TIMED_OUT)
                cancel_token = self._cancellation_tokens.get(task_id)
                if cancel_token:
                    cancel_token.cancel()
                reaped.append(task_id)
                logger.warning("DelegationCoordinator: Reaped stale task %s", task_id)
        return reaped

    def _settle_finished_stream(self, task: DelegationTask, final_reply: OutboundMessage | None) -> None:
        """Record how a finished stream ended, unless the reaper already timed the task out while it ran.

        A failed turn arrives as an ordinary reply flagged as an error; its text is already member-safe.
        """
        if task.status in _TERMINAL_STATUSES:
            return
        if final_reply is not None and is_error_reply(final_reply):
            self.update_task_status(task.task_id, DelegationStatus.FAILED, error_message=final_reply.content)
        else:
            self.update_task_status(task.task_id, DelegationStatus.COMPLETED)

    async def execute_task_lifecycle(
        self,
        task: DelegationTask,
        executor: AgentExecutor,
        bus: MessageBus,
        original_msg: InboundMessage,
    ) -> None:
        """Run the delegated task in the background, then deliver its outcome to the chat it came from."""
        self.update_task_status(task.task_id, DelegationStatus.RUNNING)
        cancel_token = self.get_cancellation_token(task.task_id)
        steering_token = self.get_steering_token(task.task_id)

        # StreamingText events are cumulative snapshots; the last OutboundMessage is the authoritative reply.
        snapshot = ""
        final_reply: OutboundMessage | None = None
        try:
            task_msg = replace(original_msg, content=task.normalized_prompt)
            async for event in executor.execute_stream(
                task_msg,
                task.origin_user_id,
                cancel_token=cancel_token,
                steering_token=steering_token,
            ):
                if isinstance(event, OutboundMessage):
                    final_reply = event
                elif isinstance(event, StreamingText):
                    snapshot = event.text
            self._settle_finished_stream(task, final_reply)
        except Exception as exc:
            safe_text, ref_id = friendly_error_message(exc, original_msg)
            logger.exception("DelegationCoordinator: Task %s failed [ref: %s]: %s", task.task_id, ref_id, exc)
            snapshot, final_reply = "", None
            if task.status not in _TERMINAL_STATUSES:
                self.update_task_status(task.task_id, DelegationStatus.FAILED, error_message=safe_text)

        await bus.publish_outbound(build_delivery_message(task, original_msg, final_reply, snapshot))
        logger.info(
            "DelegationCoordinator: Task %s finished as %s and delivered to %s",
            task.task_id,
            task.status.value,
            task.origin_chat_id,
        )
