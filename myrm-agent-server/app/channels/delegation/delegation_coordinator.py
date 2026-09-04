"""Asynchronous delegation coordinator, in-flight steering pipeline, and approval relay state machine.

Coordinates execution lifecycle of delegated tasks, bridges in-flight prompt
injections to running Agent sandboxes via SteeringToken, and coordinates
remote interactive human-in-the-loop authorization from mobile clients.

[INPUT]
- .delegation_models::DelegationTask, DelegationStatus, SteeringMessage, ApprovalRequest, ApprovalResponse, ProgressBeacon, RiskLevel
- myrm_agent_harness.utils.runtime.steering::SteeringToken
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken

[OUTPUT]
- DelegationCoordinator: Central coordinator managing task state machines, steering, and remote approvals.

[POS]
Execution lifecycle and coordination engine for app/channels/delegation/.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from .delegation_delivery import build_delivery_card_content, scan_workspace_artifacts
from .delegation_models import (
    ApprovalRequest,
    ApprovalResponse,
    DelegationStatus,
    DelegationTask,
    ProgressBeacon,
    RiskLevel,
    SteeringMessage,
)

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.protocols.agent import AgentExecutor
    from app.channels.types import InboundMessage

logger = logging.getLogger("myrm.channels.delegation.coordinator")


class DelegationCoordinator:
    """Coordinates task execution, in-flight prompt steering, and remote mobile approvals."""

    def __init__(self) -> None:
        self._tasks: dict[str, DelegationTask] = {}
        self._cancellation_tokens: dict[str, CancellationToken] = {}
        self._steering_tokens: dict[str, SteeringToken] = {}
        self._steering_history: dict[str, list[SteeringMessage]] = {}
        self._pending_approvals: dict[str, tuple[ApprovalRequest, asyncio.Future[ApprovalResponse]]] = {}
        self._beacon_listeners: list[Callable[[ProgressBeacon], None]] = []

    def register_task(self, task: DelegationTask) -> None:
        """Register a newly created delegated task."""
        self._tasks[task.task_id] = task
        self._cancellation_tokens[task.task_id] = CancellationToken()
        self._steering_tokens[task.task_id] = SteeringToken()
        self._steering_history[task.task_id] = []
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
        result_summary: str = "",
    ) -> None:
        """Transition task lifecycle status."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = status
        now = time.time()
        if status == DelegationStatus.RUNNING and task.started_at is None:
            task.started_at = now
        elif status in (DelegationStatus.COMPLETED, DelegationStatus.FAILED, DelegationStatus.CANCELLED):
            task.completed_at = now

        if error_message:
            task.error_message = error_message
        if result_summary:
            task.result_summary = result_summary

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

        msg = SteeringMessage(
            task_id=task_id,
            content=content,
            sender_id=sender_id,
        )
        self._steering_history.setdefault(task_id, []).append(msg)
        logger.info("DelegationCoordinator: Injected in-flight steering to task %s by %s", task_id, sender_id)
        return True

    def cancel_task(self, task_id: str, reason: str = "User cancelled") -> bool:
        """Cancel an active task."""
        task = self._tasks.get(task_id)
        if not task or task.status in (DelegationStatus.COMPLETED, DelegationStatus.FAILED, DelegationStatus.CANCELLED):
            return False

        cancel_token = self._cancellation_tokens.get(task_id)
        if cancel_token:
            cancel_token.cancel()

        self.update_task_status(task_id, DelegationStatus.CANCELLED, error_message=reason)
        return True

    def emit_beacon(self, task_id: str, phase: str, percent: int, milestone_message: str) -> None:
        """Broadcast progress milestone beacon."""
        beacon = ProgressBeacon(
            task_id=task_id,
            phase=phase,
            percent=max(0, min(100, percent)),
            milestone_message=milestone_message,
        )
        for listener in self._beacon_listeners:
            try:
                listener(beacon)
            except Exception as e:
                logger.error("DelegationCoordinator: Beacon listener error: %s", e)

    def add_beacon_listener(self, listener: Callable[[ProgressBeacon], None]) -> None:
        """Add a progress beacon subscriber."""
        self._beacon_listeners.append(listener)

    async def request_remote_approval(
        self,
        task_id: str,
        action_name: str,
        action_summary: str,
        *,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        options: list[str] | None = None,
        timeout_seconds: float = 300.0,
    ) -> ApprovalResponse:
        """Suspend task and await remote mobile user authorization.

        Args:
            task_id: Target task ID.
            action_name: Name of the high-risk action/tool.
            action_summary: Compact description of the action.
            risk_level: Risk severity.
            options: Allowed decision choices.
            timeout_seconds: Maximum wait duration before auto-rejecting.

        Returns:
            ApprovalResponse with user's decision.
        """
        request_id = f"appr_{uuid.uuid4().hex[:8]}"
        req = ApprovalRequest(
            request_id=request_id,
            task_id=task_id,
            action_name=action_name,
            action_summary=action_summary,
            risk_level=risk_level,
            options=options or ["approve", "reject"],
            timeout_seconds=timeout_seconds,
        )

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[ApprovalResponse] = loop.create_future()
        self._pending_approvals[request_id] = (req, fut)

        # Transition task to suspended
        prev_status = self._tasks.get(task_id).status if self._tasks.get(task_id) else DelegationStatus.RUNNING
        self.update_task_status(task_id, DelegationStatus.SUSPENDED_FOR_APPROVAL)

        try:
            resp = await asyncio.wait_for(fut, timeout=timeout_seconds)
            return resp
        except asyncio.TimeoutError:
            logger.warning("DelegationCoordinator: Approval request %s timed out after %ss", request_id, timeout_seconds)
            return ApprovalResponse(
                request_id=request_id,
                task_id=task_id,
                decision="reject",
                responder_id="system",
                note=f"Approval timed out after {timeout_seconds}s",
            )
        finally:
            self._pending_approvals.pop(request_id, None)
            if self._tasks.get(task_id) and self._tasks[task_id].status == DelegationStatus.SUSPENDED_FOR_APPROVAL:
                self.update_task_status(task_id, prev_status)

    def resolve_approval(
        self,
        request_id: str,
        decision: Literal["approve", "reject"],
        responder_id: str,
        *,
        note: str = "",
    ) -> bool:
        """Resolve a pending approval request with mobile user response."""
        item = self._pending_approvals.get(request_id)
        if not item:
            return False

        _, fut = item
        if fut.done():
            return False

        resp = ApprovalResponse(
            request_id=request_id,
            task_id=item[0].task_id,
            decision=decision,
            responder_id=responder_id,
            note=note,
        )
        fut.set_result(resp)
        logger.info("DelegationCoordinator: Resolved approval %s with decision %s by %s", request_id, decision, responder_id)
        return True

    def get_pending_approval_by_task(self, task_id: str) -> ApprovalRequest | None:
        """Get currently active pending approval request for a task."""
        for req, _ in self._pending_approvals.values():
            if req.task_id == task_id:
                return req
        return None

    def find_active_task(self, channel: str, user_id: str) -> DelegationTask | None:
        """Find the currently active or running task for a user in a channel."""
        for task in self._tasks.values():
            if (
                task.origin_channel == channel
                and task.origin_user_id == user_id
                and task.status in (DelegationStatus.PENDING, DelegationStatus.RUNNING, DelegationStatus.SUSPENDED_FOR_APPROVAL)
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
            if task.status in (DelegationStatus.COMPLETED, DelegationStatus.FAILED, DelegationStatus.CANCELLED):
                continue
            started = task.started_at or task.created_at
            timeout = task.timeout_seconds or max_age_seconds
            if now - started > timeout:
                self.update_task_status(
                    task_id,
                    DelegationStatus.FAILED,
                    error_message=f"Task timed out after {int(now - started)} seconds",
                )
                cancel_token = self._cancellation_tokens.get(task_id)
                if cancel_token:
                    cancel_token.cancel()
                reaped.append(task_id)
                logger.warning("DelegationCoordinator: Reaped stale task %s", task_id)
        return reaped

    async def execute_task_lifecycle(
        self,
        task: DelegationTask,
        executor: AgentExecutor,
        bus: MessageBus,
        original_msg: InboundMessage,
        *,
        workspace_dir: str | Path = "",
        server_base_url: str = "",
    ) -> None:
        """Run delegated task lifecycle in background, handle status transitions, and publish delivery card."""
        from dataclasses import replace

        from app.channels.types import OutboundMessage, StreamingText

        self.update_task_status(task.task_id, DelegationStatus.RUNNING)
        cancel_token = self.get_cancellation_token(task.task_id)
        steering_token = self.get_steering_token(task.task_id)

        try:
            task_msg = replace(original_msg, content=task.normalized_prompt)
            result_text = ""

            async for event in executor.execute_stream(
                task_msg,
                task.origin_user_id,
                cancel_token=cancel_token,
                steering_token=steering_token,
            ):
                if isinstance(event, StreamingText):
                    result_text += event.text

            artifacts = []
            if workspace_dir:
                artifacts = scan_workspace_artifacts(
                    workspace_dir,
                    server_base_url=server_base_url,
                )
                task.artifacts = artifacts

            self.update_task_status(
                task.task_id,
                DelegationStatus.COMPLETED,
                result_summary=result_text[:200] if result_text else "Task finished successfully.",
            )

            card_content = build_delivery_card_content(task, artifacts, server_base_url=server_base_url)
            outbound = OutboundMessage(
                channel=task.origin_channel,
                recipient_id=task.origin_chat_id,
                content=card_content,
                user_id=task.origin_user_id,
                metadata={"delegation_task_id": task.task_id, "is_delegation_delivery": True},
            )
            await bus.publish_outbound(outbound)
            logger.info("DelegationCoordinator: Task %s completed and delivered to %s", task.task_id, task.origin_chat_id)

        except Exception as exc:
            logger.exception("DelegationCoordinator: Task %s failed: %s", task.task_id, exc)
            self.update_task_status(task.task_id, DelegationStatus.FAILED, error_message=str(exc))
            fail_msg = OutboundMessage(
                channel=task.origin_channel,
                recipient_id=task.origin_chat_id,
                content=f"❌ 异步任务 `[{task.task_id}]` 执行失败：{exc}",
                user_id=task.origin_user_id,
            )
            await bus.publish_outbound(fail_msg)
