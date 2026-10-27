"""Where a message goes once a turn is already running or the sender is handing work over: steering the running turn,
handing a request to a delegated task, and steering a delegated task.

Runs the real ``AgentRouter`` dispatch with the handlers each step hands off to replaced by recorders (see
``inbound_dispatch_testkit``), so what is pinned is the order of the steps and what each one does with the message.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router import AgentRouter

from .inbound_dispatch_testkit import (
    PIPELINE,
    dispatch_router,
    gate_submissions,
    inbound_msg,
    published_messages,
    run_dispatch,
    running_turn,
)

# --- steering a running turn -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["steer", "redirect"])
async def test_text_typed_while_a_turn_runs_is_taken_in_and_acknowledged(mode: str) -> None:
    router = dispatch_router()
    token = running_turn(router, mode=mode, thread_id="th-1")

    await run_dispatch(router, inbound_msg("  focus on 2026  ", is_group=True, message_id="m-77", thread_id="th-1"))

    assert token.has_pending
    assert token.redirect_requested == (mode == "redirect")
    assert token.activate() == ["focus on 2026"]
    [reply] = published_messages(router)
    assert "focus on 2026" in reply.content
    assert (reply.channel, reply.recipient_id, reply.thread_id, reply.reply_to_id) == ("telegram", "chat-1", "th-1", "m-77")
    assert gate_submissions(router) == []


@pytest.mark.asyncio
async def test_the_acknowledgement_of_a_direct_message_quotes_nothing() -> None:
    router = dispatch_router()
    running_turn(router, mode="steer")

    await run_dispatch(router, inbound_msg("focus on 2026", user_id="owner-1"))

    [reply] = published_messages(router)
    assert reply.reply_to_id is None
    assert reply.user_id == "owner-1"


@pytest.mark.asyncio
async def test_a_long_steer_is_previewed_in_eighty_characters() -> None:
    router = dispatch_router()
    running_turn(router, mode="steer")

    await run_dispatch(router, inbound_msg("x" * 200))

    [reply] = published_messages(router)
    assert "x" * 80 + "..." in reply.content
    assert "x" * 81 not in reply.content


@pytest.mark.asyncio
async def test_the_mode_can_come_from_the_message_when_the_turn_names_none() -> None:
    router = dispatch_router()
    token = running_turn(router, mode=None)

    await run_dispatch(router, inbound_msg("narrow it down", metadata={"busy_input_mode": "steer"}))

    assert token.activate() == ["narrow it down"]
    assert gate_submissions(router) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [None, "queue"])
async def test_a_turn_without_a_steering_mode_leaves_the_message_for_the_gate(mode: str | None) -> None:
    router = dispatch_router()
    token = running_turn(router, mode=mode)

    await run_dispatch(router, inbound_msg("narrow it down"))

    assert not token.has_pending
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
async def test_a_slash_message_is_not_steered_into_the_running_turn() -> None:
    router = dispatch_router()
    token = running_turn(router, mode="steer")

    await run_dispatch(router, inbound_msg("/unknown thing"))

    assert not token.has_pending
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
async def test_steering_looks_up_the_turn_of_the_thread_the_message_is_in() -> None:
    router = dispatch_router()
    token = running_turn(router, mode="steer")  # registered under the chat, not under thread th-1

    await run_dispatch(router, inbound_msg("narrow it down", thread_id="th-1"))

    assert not token.has_pending
    assert len(gate_submissions(router)) == 1


# --- delegation ------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("handled", "submitted"), [(True, 0), (False, 1)])
async def test_the_owners_delegation_request_is_handed_over_with_its_prompt(handled: bool, submitted: int) -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    router._handle_delegation_inbound = AsyncMock(return_value=handled)

    await run_dispatch(router, inbound_msg("/delegate summarise the report"))

    router._handle_delegation_inbound.assert_awaited_once()
    assert router._handle_delegation_inbound.await_args.args[1] == "summarise the report"
    assert len(gate_submissions(router)) == submitted


@pytest.mark.asyncio
async def test_a_delegation_request_from_anyone_else_is_an_ordinary_turn() -> None:
    router = dispatch_router()

    await run_dispatch(router, inbound_msg("/delegate summarise the report"))

    router._handle_delegation_inbound.assert_not_awaited()
    assert published_messages(router) == []
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
async def test_a_delegation_request_without_a_task_is_answered_with_what_is_missing() -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)

    await run_dispatch(router, inbound_msg("/delegate", thread_id="th-1", user_id="owner-1"))

    router._handle_delegation_inbound.assert_not_awaited()
    [reply] = published_messages(router)
    assert (reply.channel, reply.recipient_id, reply.thread_id, reply.user_id) == ("telegram", "chat-1", "th-1", "owner-1")
    assert reply.reply_to_id is None
    assert gate_submissions(router) == []


@pytest.mark.asyncio
async def test_a_delegation_intent_below_the_confidence_bar_is_an_ordinary_turn() -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)

    with patch(f"{PIPELINE}.is_delegation_intent", return_value=(True, 0.8, "do it")):
        await run_dispatch(router, inbound_msg("maybe do it later"))

    router._handle_delegation_inbound.assert_not_awaited()
    assert len(gate_submissions(router)) == 1


# --- steering a delegated task ---------------------------------------------------------------------------------------


def _delegated_task(router: AgentRouter, *, injected: bool) -> MagicMock:
    coordinator = cast(MagicMock, router._delegation_coordinator)
    coordinator.find_active_task.return_value = SimpleNamespace(task_id="task-9")
    coordinator.inject_steering.return_value = injected
    return coordinator


@pytest.mark.asyncio
async def test_text_for_a_running_delegated_task_is_injected_and_acknowledged() -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)

    await run_dispatch(router, inbound_msg("  also check the totals  ", thread_id="th-1", user_id="owner-1"))

    coordinator.find_active_task.assert_called_once_with("telegram", "chat-1", "owner-1")
    coordinator.inject_steering.assert_called_once_with("task-9", "also check the totals", "owner-1")
    [reply] = published_messages(router)
    assert "task-9" in reply.content
    assert (reply.recipient_id, reply.thread_id, reply.reply_to_id) == ("chat-1", "th-1", None)
    assert gate_submissions(router) == []


@pytest.mark.asyncio
async def test_the_task_is_looked_up_for_the_sender_when_the_message_names_no_user() -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)

    await run_dispatch(router, inbound_msg("also check the totals"))

    coordinator.find_active_task.assert_called_once_with("telegram", "chat-1", "u1")


@pytest.mark.asyncio
async def test_text_a_delegated_task_refuses_continues_as_an_ordinary_turn() -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    _delegated_task(router, injected=False)

    await run_dispatch(router, inbound_msg("also check the totals"))

    assert published_messages(router) == []
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
async def test_a_turn_registered_in_the_chat_keeps_the_text_from_the_delegated_task() -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)
    running_turn(router, mode=None)

    await run_dispatch(router, inbound_msg("also check the totals"))

    coordinator.inject_steering.assert_not_called()
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("content", "owner"), [("/unknown thing", True), ("also check the totals", False)])
async def test_only_the_owners_plain_text_steers_a_delegated_task(content: str, owner: bool) -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=owner)
    coordinator = _delegated_task(router, injected=True)

    await run_dispatch(router, inbound_msg(content))

    coordinator.inject_steering.assert_not_called()
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
async def test_a_running_turn_is_steered_before_a_delegated_task_is_considered() -> None:
    router = dispatch_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)
    token = running_turn(router, mode="steer")

    await run_dispatch(router, inbound_msg("also check the totals"))

    assert token.activate() == ["also check the totals"]
    coordinator.find_active_task.assert_not_called()
