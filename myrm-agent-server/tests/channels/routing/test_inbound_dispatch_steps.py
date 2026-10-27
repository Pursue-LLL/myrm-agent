"""Where one consumed inbound message goes: each routing step claims it or lets it reach the next, ending at the session gate.

Runs the real ``AgentRouter`` dispatch with the handlers each step hands off to replaced by recorders, so what is pinned
is the order of the steps and what each one does with the message, not what the handlers do.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage, OutboundMessage

from .risk_gate_testkit import make_router

_PIPELINE = "app.channels.routing.pipeline.inbound"


def _msg(
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


def _router() -> AgentRouter:
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


def _running_turn(router: AgentRouter, *, mode: str | None, thread_id: str | None = None) -> SteeringToken:
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


def _published(router: AgentRouter) -> list[OutboundMessage]:
    return [call.args[0] for call in router._bus.publish_outbound.await_args_list]


def _submitted(router: AgentRouter) -> list[InboundMessage]:
    return [call.args[0] for call in router._gate.submit.call_args_list]


async def _dispatch(router: AgentRouter, msg: InboundMessage) -> None:
    await router._dispatch_inbound_message(msg)
    await asyncio.sleep(0)  # a step that hands off to a task runs it before the assertions


# --- the end of the line ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_plain_message_reaches_the_session_gate_with_its_locale_resolved() -> None:
    router = _router()

    await _dispatch(router, _msg("what is the weather"))

    [submitted] = _submitted(router)
    assert submitted.content == "what is the weather"
    assert submitted.metadata["locale"]
    router._handle_approval_command.assert_not_awaited()
    router._dispatch_resolved.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_duplicate_is_dropped_before_any_step_sees_it() -> None:
    router = _router()

    await _dispatch(router, _msg("hello"))
    await _dispatch(router, _msg("hello"))

    assert len(_submitted(router)) == 1


# --- group activity --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_group", "has_resolver", "noted"),
    [(True, True, True), (True, False, False), (False, True, False)],
    ids=["group-with-topics", "group-without-topic-manager", "direct-chat"],
)
async def test_group_activity_is_noted_only_in_a_group_with_a_topic_manager(
    is_group: bool, has_resolver: bool, noted: bool
) -> None:
    router = _router()
    router._topic_resolver = MagicMock() if has_resolver else None

    with (
        patch("app.channels.routing.follow_up.note_group_activity") as note,
        patch("app.channels.routing.follow_up.scan_stalled_threads", new=AsyncMock()) as scan,
    ):
        await _dispatch(router, _msg("hello team", is_group=is_group, sender_name="Ann", thread_id="th-1"))

    assert note.call_count == int(noted)
    assert scan.await_count == int(noted)
    if noted:
        assert note.call_args.args[:5] == ("telegram", "chat-1", "th-1", "u1", "Ann")
    assert len(_submitted(router)) == 1, "noting activity never claims the message"


# --- approvals -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_action_button_click_on_an_approval_is_handled_and_goes_no_further() -> None:
    router = _router()

    await _dispatch(router, _msg("approval:approve:rec-1", metadata={"callback_prefix": "act"}))

    router._handle_action_button_approval.assert_awaited_once()
    assert _submitted(router) == []


@pytest.mark.asyncio
async def test_an_action_button_that_is_not_an_approval_continues_down_the_line() -> None:
    router = _router()

    await _dispatch(router, _msg("menu:open", metadata={"callback_prefix": "act"}))

    router._handle_action_button_approval.assert_not_awaited()
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_a_reaction_is_never_a_turn_and_is_an_approval_only_when_it_is_valid(valid: bool) -> None:
    router = _router()
    router._is_reaction_approval_valid = MagicMock(return_value=valid)

    await _dispatch(router, _msg("👍", metadata={"reaction": True}))

    assert router._handle_approval_command.await_count == int(valid)
    assert _submitted(router) == []
    router._dispatch_resolved.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reaction_that_is_no_approval_word_is_dropped_quietly() -> None:
    router = _router()
    router._is_reaction_approval_valid = MagicMock(return_value=True)

    await _dispatch(router, _msg("lol", metadata={"reaction": True}))

    router._handle_approval_command.assert_not_awaited()
    assert _submitted(router) == []


@pytest.mark.asyncio
async def test_an_explicit_approval_command_is_handled_without_a_pending_request() -> None:
    router = _router()
    router._has_pending_approval = MagicMock(return_value=False)

    await _dispatch(router, _msg("/approve"))

    router._handle_approval_command.assert_awaited_once()
    router._dispatch_resolved.assert_not_awaited()
    assert _submitted(router) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("pending", "handled"), [(True, True), (False, False)])
async def test_a_bare_shortcut_is_an_approval_only_while_one_is_open(pending: bool, handled: bool) -> None:
    router = _router()
    router._has_pending_approval = MagicMock(return_value=pending)

    await _dispatch(router, _msg("1"))

    assert router._handle_approval_command.await_count == int(handled)
    assert len(_submitted(router)) == int(not handled)


# --- commands --------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_slash_command_that_the_registry_handles_never_reaches_the_gate() -> None:
    router = _router()

    await _dispatch(router, _msg("/help"))

    router._dispatch_resolved.assert_awaited_once()
    assert _submitted(router) == []


@pytest.mark.asyncio
async def test_a_slash_command_the_handler_declines_continues_as_an_ordinary_message() -> None:
    router = _router()
    router._dispatch_resolved = AsyncMock(return_value=False)

    await _dispatch(router, _msg("/help"))

    router._dispatch_resolved.assert_awaited_once()
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
async def test_a_raw_shell_command_is_answered_and_never_reaches_the_gate() -> None:
    router = _router()

    await _dispatch(router, _msg("!bash ls"))

    router._handle_bang_command.assert_awaited_once()
    assert _submitted(router) == []


# --- event triggers --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("admitted", "untrusted"), [(True, False), (True, True), (False, False)])
async def test_event_triggers_run_for_an_admitted_sender_under_the_senders_fence(admitted: bool, untrusted: bool) -> None:
    router = _router()
    router._is_sender_admitted = AsyncMock(return_value=admitted)
    router._is_untrusted_event_sender = AsyncMock(return_value=untrusted)

    with patch(f"{_PIPELINE}.dispatch_cron_event_for_inbound_message", new=AsyncMock()) as dispatch:
        await _dispatch(router, _msg("deploy now"))

    if admitted:
        dispatch.assert_awaited_once_with("deploy now", "telegram", "", untrusted=untrusted)
    else:
        dispatch.assert_not_awaited()
    assert len(_submitted(router)) == 1, "an event trigger never claims the message"


@pytest.mark.asyncio
async def test_event_triggers_see_a_message_that_is_then_steered_into_the_running_turn() -> None:
    router = _router()
    router._is_sender_admitted = AsyncMock(return_value=True)
    router._is_untrusted_event_sender = AsyncMock(return_value=False)
    token = _running_turn(router, mode="steer")

    with patch(f"{_PIPELINE}.dispatch_cron_event_for_inbound_message", new=AsyncMock()) as dispatch:
        await _dispatch(router, _msg("only the 2026 rows"))

    dispatch.assert_awaited_once()
    assert token.activate() == ["only the 2026 rows"]


# --- steering a running turn -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["steer", "redirect"])
async def test_text_typed_while_a_turn_runs_is_taken_in_and_acknowledged(mode: str) -> None:
    router = _router()
    token = _running_turn(router, mode=mode, thread_id="th-1")

    await _dispatch(router, _msg("  focus on 2026  ", is_group=True, message_id="m-77", thread_id="th-1"))

    assert token.has_pending
    assert token.redirect_requested == (mode == "redirect")
    assert token.activate() == ["focus on 2026"]
    [reply] = _published(router)
    assert "focus on 2026" in reply.content
    assert (reply.channel, reply.recipient_id, reply.thread_id, reply.reply_to_id) == ("telegram", "chat-1", "th-1", "m-77")
    assert _submitted(router) == []


@pytest.mark.asyncio
async def test_the_acknowledgement_of_a_direct_message_quotes_nothing() -> None:
    router = _router()
    _running_turn(router, mode="steer")

    await _dispatch(router, _msg("focus on 2026", user_id="owner-1"))

    [reply] = _published(router)
    assert reply.reply_to_id is None
    assert reply.user_id == "owner-1"


@pytest.mark.asyncio
async def test_a_long_steer_is_previewed_in_eighty_characters() -> None:
    router = _router()
    _running_turn(router, mode="steer")

    await _dispatch(router, _msg("x" * 200))

    [reply] = _published(router)
    assert "x" * 80 + "..." in reply.content
    assert "x" * 81 not in reply.content


@pytest.mark.asyncio
async def test_the_mode_can_come_from_the_message_when_the_turn_names_none() -> None:
    router = _router()
    token = _running_turn(router, mode=None)

    await _dispatch(router, _msg("narrow it down", metadata={"busy_input_mode": "steer"}))

    assert token.activate() == ["narrow it down"]
    assert _submitted(router) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [None, "queue"])
async def test_a_turn_without_a_steering_mode_leaves_the_message_for_the_gate(mode: str | None) -> None:
    router = _router()
    token = _running_turn(router, mode=mode)

    await _dispatch(router, _msg("narrow it down"))

    assert not token.has_pending
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
async def test_a_slash_message_is_not_steered_into_the_running_turn() -> None:
    router = _router()
    token = _running_turn(router, mode="steer")

    await _dispatch(router, _msg("/unknown thing"))

    assert not token.has_pending
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
async def test_steering_looks_up_the_turn_of_the_thread_the_message_is_in() -> None:
    router = _router()
    token = _running_turn(router, mode="steer")  # registered under the chat, not under thread th-1

    await _dispatch(router, _msg("narrow it down", thread_id="th-1"))

    assert not token.has_pending
    assert len(_submitted(router)) == 1


# --- delegation ------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("handled", "submitted"), [(True, 0), (False, 1)])
async def test_the_owners_delegation_request_is_handed_over_with_its_prompt(handled: bool, submitted: int) -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)
    router._handle_delegation_inbound = AsyncMock(return_value=handled)

    await _dispatch(router, _msg("/delegate summarise the report"))

    router._handle_delegation_inbound.assert_awaited_once()
    assert router._handle_delegation_inbound.await_args.args[1] == "summarise the report"
    assert len(_submitted(router)) == submitted


@pytest.mark.asyncio
async def test_a_delegation_request_from_anyone_else_is_an_ordinary_turn() -> None:
    router = _router()

    await _dispatch(router, _msg("/delegate summarise the report"))

    router._handle_delegation_inbound.assert_not_awaited()
    assert _published(router) == []
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
async def test_a_delegation_request_without_a_task_is_answered_with_what_is_missing() -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)

    await _dispatch(router, _msg("/delegate", thread_id="th-1", user_id="owner-1"))

    router._handle_delegation_inbound.assert_not_awaited()
    [reply] = _published(router)
    assert (reply.channel, reply.recipient_id, reply.thread_id, reply.user_id) == ("telegram", "chat-1", "th-1", "owner-1")
    assert reply.reply_to_id is None
    assert _submitted(router) == []


@pytest.mark.asyncio
async def test_a_delegation_intent_below_the_confidence_bar_is_an_ordinary_turn() -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)

    with patch(f"{_PIPELINE}.is_delegation_intent", return_value=(True, 0.8, "do it")):
        await _dispatch(router, _msg("maybe do it later"))

    router._handle_delegation_inbound.assert_not_awaited()
    assert len(_submitted(router)) == 1


# --- steering a delegated task ---------------------------------------------------------------------------------------


def _delegated_task(router: AgentRouter, *, injected: bool) -> MagicMock:
    coordinator = router._delegation_coordinator
    coordinator.find_active_task.return_value = SimpleNamespace(task_id="task-9")
    coordinator.inject_steering.return_value = injected
    return coordinator


@pytest.mark.asyncio
async def test_text_for_a_running_delegated_task_is_injected_and_acknowledged() -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)

    await _dispatch(router, _msg("  also check the totals  ", thread_id="th-1", user_id="owner-1"))

    coordinator.find_active_task.assert_called_once_with("telegram", "chat-1", "owner-1")
    coordinator.inject_steering.assert_called_once_with("task-9", "also check the totals", "owner-1")
    [reply] = _published(router)
    assert "task-9" in reply.content
    assert (reply.recipient_id, reply.thread_id, reply.reply_to_id) == ("chat-1", "th-1", None)
    assert _submitted(router) == []


@pytest.mark.asyncio
async def test_the_task_is_looked_up_for_the_sender_when_the_message_names_no_user() -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)

    await _dispatch(router, _msg("also check the totals"))

    coordinator.find_active_task.assert_called_once_with("telegram", "chat-1", "u1")


@pytest.mark.asyncio
async def test_text_a_delegated_task_refuses_continues_as_an_ordinary_turn() -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)
    _delegated_task(router, injected=False)

    await _dispatch(router, _msg("also check the totals"))

    assert _published(router) == []
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
async def test_a_turn_registered_in_the_chat_keeps_the_text_from_the_delegated_task() -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)
    _running_turn(router, mode=None)

    await _dispatch(router, _msg("also check the totals"))

    coordinator.inject_steering.assert_not_called()
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("content", "owner"), [("/unknown thing", True), ("also check the totals", False)])
async def test_only_the_owners_plain_text_steers_a_delegated_task(content: str, owner: bool) -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=owner)
    coordinator = _delegated_task(router, injected=True)

    await _dispatch(router, _msg(content))

    coordinator.inject_steering.assert_not_called()
    assert len(_submitted(router)) == 1


@pytest.mark.asyncio
async def test_a_running_turn_is_steered_before_a_delegated_task_is_considered() -> None:
    router = _router()
    router._check_admin_permission = AsyncMock(return_value=True)
    coordinator = _delegated_task(router, injected=True)
    token = _running_turn(router, mode="steer")

    await _dispatch(router, _msg("also check the totals"))

    assert token.activate() == ["also check the totals"]
    coordinator.find_active_task.assert_not_called()
