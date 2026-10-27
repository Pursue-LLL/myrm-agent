"""Asynchronous delegation coordinator and in-flight steering pipeline.

Coordinates execution lifecycle of delegated tasks and bridges in-flight prompt
injections to running Agent sandboxes via SteeringToken.

[INPUT]
- .delegation_models::DelegationTask, DelegationStatus
- .delegation_heartbeat::delegated_run_heartbeat (POS: tells the chat the run is still working)
- app.channels.routing.friendly_errors::friendly_error_message, is_error_reply (POS: member-safe failure wording and failed-turn flag)
- app.channels.types::METADATA_APPROVAL_WINDOW_SECONDS_KEY (POS: lets a run wait for a tool approval as long as the task may run)
- myrm_agent_harness.utils.runtime.steering::SteeringToken
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken

[OUTPUT]
- ApprovalHandOver: callback through which a run that stopped at a tool approval is handed to the chat it came from.
- DelegationCoordinator: Central coordinator managing task state machines, steering, stopping, interruption at shutdown, and the background execution lifecycle.

[POS]
Execution lifecycle and coordination engine for app/channels/delegation/.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.routing.friendly_errors import friendly_error_message, is_error_reply
from app.channels.types import METADATA_APPROVAL_WINDOW_SECONDS_KEY, OutboundMessage, ProgressUpdate, StreamingText

from .delegation_delivery import build_delivery_message
from .delegation_heartbeat import delegated_run_heartbeat
from .delegation_models import DelegationStatus, DelegationTask

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.protocols.agent import AgentExecutor
    from app.channels.types import InboundMessage

logger = logging.getLogger("myrm.channels.delegation.coordinator")

_TERMINAL_STATUSES = (
    DelegationStatus.COMPLETED,
    DelegationStatus.FAILED,
    DelegationStatus.TIMED_OUT,
    DelegationStatus.CANCELLED,
    DelegationStatus.INTERRUPTED,
)

ApprovalHandOver = Callable[[ProgressUpdate], Awaitable[None]]
"""Puts the approval request in front of the chat so the user's answer resumes the run there."""


class DelegationCoordinator:
    """Coordinates task execution and in-flight prompt steering."""

    def __init__(self) -> None:
        self._tasks: dict[str, DelegationTask] = {}
        self._cancellation_tokens: dict[str, CancellationToken] = {}
        self._steering_tokens: dict[str, SteeringToken] = {}
        self._runners: dict[str, asyncio.Task[object]] = {}

    def register_task(self, task: DelegationTask) -> None:
        """Register a newly created delegated task."""
        self._tasks[task.task_id] = task
        self._cancellation_tokens[task.task_id] = CancellationToken()
        self._steering_tokens[task.task_id] = SteeringToken()
        logger.info("DelegationCoordinator: Registered task %s for user %s", task.task_id, task.origin_user_id)

    def get_task(self, task_id: str) -> DelegationTask | None:
        """Retrieve task by ID."""
        return self._tasks.get(task_id)

    def _forget(self, task_id: str) -> None:
        """Drop everything held for a task whose outcome has been handled."""
        self._tasks.pop(task_id, None)
        self._cancellation_tokens.pop(task_id, None)
        self._steering_tokens.pop(task_id, None)
        self._runners.pop(task_id, None)

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

    def find_active_task(self, channel: str, chat_id: str, user_id: str) -> DelegationTask | None:
        """Find the pending or running task the user delegated from this chat."""
        for task in self._tasks.values():
            if (
                task.origin_channel == channel
                and task.origin_chat_id == chat_id
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

    def _interrupt(self, task_id: str, reason: str) -> None:
        """Stop a run the way the router stops a foreground turn: the token for a cooperative exit, the task for a run that never checks it."""
        cancel_token = self._cancellation_tokens.get(task_id)
        if cancel_token:
            cancel_token.cancel(reason)
        runner = self._runners.get(task_id)
        if runner and not runner.done():
            runner.cancel()

    def running_task_ids(self, channel: str, chat_id: str, user_id: str) -> list[str]:
        """IDs of the running tasks the user delegated from this chat: the ones their next ``/stop`` ends."""
        return [
            task.task_id
            for task in self._tasks.values()
            if task.origin_channel == channel
            and task.origin_chat_id == chat_id
            and task.origin_user_id == user_id
            and task.status is DelegationStatus.RUNNING
        ]

    def cancel_for_chat(self, channel: str, chat_id: str, user_id: str) -> list[str]:
        """Stop the running tasks the user delegated from this chat.

        Returns:
            IDs of the tasks that were stopped; the caller tells the user.
        """
        stopped = self.running_task_ids(channel, chat_id, user_id)
        for task_id in stopped:
            self.update_task_status(task_id, DelegationStatus.CANCELLED)
            self._interrupt(task_id, "User /stop command")
        return stopped

    def reap_stale_tasks(self, max_age_seconds: float = 7200.0) -> list[str]:
        """Time out and stop the tasks that have run past their limit.

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
                self._interrupt(task_id, "Delegated task exceeded its time limit")
                reaped.append(task_id)
                logger.warning("DelegationCoordinator: Reaped stale task %s", task_id)
        return reaped

    async def interrupt_all(self, *, grace_seconds: float = 5.0) -> list[str]:
        """Stop every running task because the service is going down; each run tells its chat before it ends.

        The notices are queued while the channels are still up. A run that does not settle within the grace period
        is left to the cancellation already delivered to it, so a stuck run cannot hold the shutdown.

        Returns:
            IDs of the interrupted tasks.
        """
        interrupted = [task.task_id for task in self._tasks.values() if task.status is DelegationStatus.RUNNING]
        runners = [runner for task_id in interrupted if (runner := self._runners.get(task_id)) is not None]
        for task_id in interrupted:
            self.update_task_status(task_id, DelegationStatus.INTERRUPTED)
            self._interrupt(task_id, "Service stopping")
        if runners:
            await asyncio.wait(runners, timeout=grace_seconds)
        return interrupted

    def _settle_finished_stream(self, task: DelegationTask, final_reply: OutboundMessage | None) -> None:
        """Record how a finished stream ended, unless the task was already timed out or stopped while it ran.

        A failed turn arrives as an ordinary reply flagged as an error; its text is already member-safe.
        """
        if task.status in _TERMINAL_STATUSES:
            return
        if final_reply is not None and is_error_reply(final_reply):
            self.update_task_status(task.task_id, DelegationStatus.FAILED, error_message=final_reply.content)
        else:
            self.update_task_status(task.task_id, DelegationStatus.COMPLETED)

    async def _settle_interrupted(self, task: DelegationTask, bus: MessageBus, original_msg: InboundMessage) -> None:
        """Close a run whose task was cancelled: a timed-out or interrupted run tells its chat why; a stopped one was already answered by /stop."""
        try:
            if task.status in (DelegationStatus.TIMED_OUT, DelegationStatus.INTERRUPTED):
                await bus.publish_outbound(build_delivery_message(task, original_msg, None, ""))
            elif task.status not in _TERMINAL_STATUSES:
                self.update_task_status(task.task_id, DelegationStatus.CANCELLED)
        except Exception:
            logger.warning(
                "DelegationCoordinator: Task %s ended as %s without its notice", task.task_id, task.status.value, exc_info=True
            )
        finally:
            self._forget(task.task_id)

    async def execute_task_lifecycle(
        self,
        task: DelegationTask,
        executor: AgentExecutor,
        bus: MessageBus,
        original_msg: InboundMessage,
        *,
        hand_over_approval: ApprovalHandOver,
    ) -> None:
        """Run the delegated task in the background, then deliver its outcome to the chat it came from.

        A run that stops at a tool approval has not finished: the request is handed to the chat through
        ``hand_over_approval`` and the user's answer resumes the run there as an ordinary turn.
        """
        runner = asyncio.current_task()
        if runner is not None:
            self._runners[task.task_id] = runner
        self.update_task_status(task.task_id, DelegationStatus.RUNNING)
        cancel_token = self.get_cancellation_token(task.task_id)
        steering_token = self.get_steering_token(task.task_id)

        # StreamingText events are cumulative snapshots; the last OutboundMessage is the authoritative reply.
        snapshot = ""
        final_reply: OutboundMessage | None = None
        approval_request: ProgressUpdate | None = None
        stopped_at_approval = False
        try:
            # The requester is not watching the chat, so a tool approval may wait as long as the task itself may run.
            task_msg = replace(
                original_msg,
                content=task.prompt,
                metadata={**original_msg.metadata, METADATA_APPROVAL_WINDOW_SECONDS_KEY: task.timeout_seconds},
            )
            async with delegated_run_heartbeat(task, bus, original_msg) as note_progress:
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
                    elif isinstance(event, ProgressUpdate):
                        note_progress(event)
                        if event.quick_replies:
                            approval_request = event
            self._settle_finished_stream(task, final_reply)
            if approval_request is not None and task.status is DelegationStatus.COMPLETED:
                await hand_over_approval(approval_request)
                stopped_at_approval = True
        except asyncio.CancelledError:
            await self._settle_interrupted(task, bus, original_msg)
            raise
        except Exception as exc:
            safe_text, ref_id = friendly_error_message(exc, original_msg)
            logger.exception("DelegationCoordinator: Task %s failed [ref: %s]: %s", task.task_id, ref_id, exc)
            snapshot, final_reply = "", None
            # A task the reaper or /stop already ended keeps that outcome; a failed hand-over undoes COMPLETED.
            if task.status in (DelegationStatus.RUNNING, DelegationStatus.COMPLETED):
                self.update_task_status(task.task_id, DelegationStatus.FAILED, error_message=safe_text)

        # Nothing is delivered for a run handed over at an approval (it has not finished) or stopped by the user
        # (``/stop`` already answered, and what the run left behind is not an answer).
        deliver = not stopped_at_approval and task.status is not DelegationStatus.CANCELLED
        try:
            if deliver:
                await bus.publish_outbound(build_delivery_message(task, original_msg, final_reply, snapshot))
        finally:
            self._forget(task.task_id)
        logger.info(
            "DelegationCoordinator: Task %s ended as %s; %s",
            task.task_id,
            task.status.value,
            f"delivered to {task.origin_chat_id}" if deliver else "nothing to deliver",
        )
