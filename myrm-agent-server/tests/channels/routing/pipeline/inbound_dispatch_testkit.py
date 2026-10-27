"""Shared fixtures for the inbound-dispatch step tests: a message builder, a router whose handlers are recorders, and
the helpers that read what a dispatch published or handed to the session gate."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage, OutboundMessage

from ..risk_gate_testkit import make_router

PIPELINE = "app.channels.routing.pipeline.inbound"


def inbound_msg(
    content: str,
    *,
    message_id: str = "m1",
    is_group: bool = False,
    thread_id: str | None = None,
    user_id: str | None = None,
    sender_name: str = "",
    metadata: dict[str, object] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="chat-1",
        content=content,
        message_id=message_id,
        is_group=is_group,
        thread_id=thread_id,
        user_id=user_id,
        sender_name=sender_name,
        metadata=metadata or {},
    )


def dispatch_router() -> AgentRouter:
    """A router whose sender checks are decided, whose gate is a recorder, and whose handlers record their calls."""
    router = make_router()
    router._is_sender_admitted = AsyncMock(return_value=False)
    router._check_admin_permission = AsyncMock(return_value=False)
    router._gate = MagicMock()
    router._handle_action_button_approval = AsyncMock()
    router._handle_approval_command = AsyncMock()
    router._dispatch_resolved = AsyncMock(return_value=True)
    router._handle_bang_command = AsyncMock()
    router._handle_delegation_inbound = AsyncMock(return_value=True)
    router._delegation_coordinator = MagicMock()
    router._delegation_coordinator.find_active_task.return_value = None
    return router


def running_turn(router: AgentRouter, *, mode: str | None, thread_id: str | None = None) -> SteeringToken:
    token = SteeringToken()
    task = asyncio.current_task()
    assert task is not None
    router._active_tasks[routing_state_key("telegram", "chat-1", thread_id)] = _ActiveTask(
        task=task,
        cancel_token=CancellationToken(),
        channel="telegram",
        chat_id="chat-1",
        placeholder_id=None,
        started_at=0.0,
        steering_token=token,
        busy_input_mode=mode,
    )
    return token


def published_messages(router: AgentRouter) -> list[OutboundMessage]:
    return [call.args[0] for call in router._bus.publish_outbound.await_args_list]


def gate_submissions(router: AgentRouter) -> list[InboundMessage]:
    return [call.args[0] for call in router._gate.submit.call_args_list]


async def run_dispatch(router: AgentRouter, msg: InboundMessage) -> None:
    await router._dispatch_inbound_message(msg)
    await asyncio.sleep(0)  # a step that hands off to a task runs it before the assertions
