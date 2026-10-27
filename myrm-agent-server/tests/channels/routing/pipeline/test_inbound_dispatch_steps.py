"""Where one consumed inbound message goes: each routing step claims it or lets it reach the next, ending at the session gate.

Runs the real ``AgentRouter`` dispatch with the handlers each step hands off to replaced by recorders, so what is pinned
is the order of the steps and what each one does with the message, not what the handlers do. This module covers the
steps before a running turn is considered: duplicates, group activity, approvals, commands and event triggers, and the
sender checks that must fail closed without dropping the message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .inbound_dispatch_testkit import (
    PIPELINE,
    dispatch_router,
    gate_submissions,
    inbound_msg,
    run_dispatch,
    running_turn,
)

# --- the end of the line ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_plain_message_reaches_the_session_gate_with_its_locale_resolved() -> None:
    router = dispatch_router()

    await run_dispatch(router, inbound_msg("what is the weather"))

    [submitted] = gate_submissions(router)
    assert submitted.content == "what is the weather"
    assert submitted.metadata["locale"]
    router._handle_approval_command.assert_not_awaited()
    router._dispatch_resolved.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_duplicate_is_dropped_before_any_step_sees_it() -> None:
    router = dispatch_router()

    await run_dispatch(router, inbound_msg("hello"))
    await run_dispatch(router, inbound_msg("hello"))

    assert len(gate_submissions(router)) == 1


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
    router = dispatch_router()
    router._topic_resolver = MagicMock() if has_resolver else None

    with (
        patch("app.channels.routing.follow_up.note_group_activity") as note,
        patch("app.channels.routing.follow_up.scan_stalled_threads", new=AsyncMock()) as scan,
    ):
        await run_dispatch(router, inbound_msg("hello team", is_group=is_group, sender_name="Ann", thread_id="th-1"))

    assert note.call_count == int(noted)
    assert scan.await_count == int(noted)
    if noted:
        assert note.call_args.args[:5] == ("telegram", "chat-1", "th-1", "u1", "Ann")
    assert len(gate_submissions(router)) == 1, "noting activity never claims the message"


# --- approvals -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_action_button_click_on_an_approval_is_handled_and_goes_no_further() -> None:
    router = dispatch_router()

    await run_dispatch(router, inbound_msg("approval:approve:rec-1", metadata={"callback_prefix": "act"}))

    router._handle_action_button_approval.assert_awaited_once()
    assert gate_submissions(router) == []


@pytest.mark.asyncio
async def test_an_action_button_that_is_not_an_approval_continues_down_the_line() -> None:
    router = dispatch_router()

    await run_dispatch(router, inbound_msg("menu:open", metadata={"callback_prefix": "act"}))

    router._handle_action_button_approval.assert_not_awaited()
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_a_reaction_is_never_a_turn_and_is_an_approval_only_when_it_is_valid(valid: bool) -> None:
    router = dispatch_router()
    router._is_reaction_approval_valid = MagicMock(return_value=valid)

    await run_dispatch(router, inbound_msg("👍", metadata={"reaction": True}))

    assert router._handle_approval_command.await_count == int(valid)
    assert gate_submissions(router) == []
    router._dispatch_resolved.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reaction_that_is_no_approval_word_is_dropped_quietly() -> None:
    router = dispatch_router()
    router._is_reaction_approval_valid = MagicMock(return_value=True)

    await run_dispatch(router, inbound_msg("lol", metadata={"reaction": True}))

    router._handle_approval_command.assert_not_awaited()
    assert gate_submissions(router) == []


@pytest.mark.asyncio
async def test_an_explicit_approval_command_is_handled_without_a_pending_request() -> None:
    router = dispatch_router()
    router._has_pending_approval = MagicMock(return_value=False)

    await run_dispatch(router, inbound_msg("/approve"))

    router._handle_approval_command.assert_awaited_once()
    router._dispatch_resolved.assert_not_awaited()
    assert gate_submissions(router) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("pending", "handled"), [(True, True), (False, False)])
async def test_a_bare_shortcut_is_an_approval_only_while_one_is_open(pending: bool, handled: bool) -> None:
    router = dispatch_router()
    router._has_pending_approval = MagicMock(return_value=pending)

    await run_dispatch(router, inbound_msg("1"))

    assert router._handle_approval_command.await_count == int(handled)
    assert len(gate_submissions(router)) == int(not handled)


# --- commands --------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_slash_command_that_the_registry_handles_never_reaches_the_gate() -> None:
    router = dispatch_router()

    await run_dispatch(router, inbound_msg("/help"))

    router._dispatch_resolved.assert_awaited_once()
    assert gate_submissions(router) == []


@pytest.mark.asyncio
async def test_a_slash_command_the_handler_declines_continues_as_an_ordinary_message() -> None:
    router = dispatch_router()
    router._dispatch_resolved = AsyncMock(return_value=False)

    await run_dispatch(router, inbound_msg("/help"))

    router._dispatch_resolved.assert_awaited_once()
    assert len(gate_submissions(router)) == 1


@pytest.mark.asyncio
async def test_a_raw_shell_command_is_answered_and_never_reaches_the_gate() -> None:
    router = dispatch_router()

    await run_dispatch(router, inbound_msg("!bash ls"))

    router._handle_bang_command.assert_awaited_once()
    assert gate_submissions(router) == []


# --- event triggers --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("admitted", "untrusted"), [(True, False), (True, True), (False, False)])
async def test_event_triggers_run_for_an_admitted_sender_under_the_senders_fence(admitted: bool, untrusted: bool) -> None:
    router = dispatch_router()
    router._is_sender_admitted = AsyncMock(return_value=admitted)
    router._is_untrusted_event_sender = AsyncMock(return_value=untrusted)

    with patch(f"{PIPELINE}.dispatch_cron_event_for_inbound_message", new=AsyncMock()) as dispatch:
        await run_dispatch(router, inbound_msg("deploy now"))

    if admitted:
        dispatch.assert_awaited_once_with("deploy now", "telegram", "", untrusted=untrusted)
    else:
        dispatch.assert_not_awaited()
    assert len(gate_submissions(router)) == 1, "an event trigger never claims the message"


@pytest.mark.asyncio
async def test_event_triggers_see_a_message_that_is_then_steered_into_the_running_turn() -> None:
    router = dispatch_router()
    router._is_sender_admitted = AsyncMock(return_value=True)
    router._is_untrusted_event_sender = AsyncMock(return_value=False)
    token = running_turn(router, mode="steer")

    with patch(f"{PIPELINE}.dispatch_cron_event_for_inbound_message", new=AsyncMock()) as dispatch:
        await run_dispatch(router, inbound_msg("only the 2026 rows"))

    dispatch.assert_awaited_once()
    assert token.activate() == ["only the 2026 rows"]


# --- sender checks that fail -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failing_admission_check_skips_the_event_triggers_but_not_the_message() -> None:
    router = dispatch_router()
    del router._is_sender_admitted  # the real check, asking a resolver that raises
    router._resolver.is_sender_admitted = AsyncMock(side_effect=RuntimeError("store down"))

    with patch(f"{PIPELINE}.dispatch_cron_event_for_inbound_message", new=AsyncMock()) as dispatch:
        await run_dispatch(router, inbound_msg("what is the weather tomorrow"))

    dispatch.assert_not_awaited()
    assert len(gate_submissions(router)) == 1, "an error in the check must not end the dispatch before the gate"


@pytest.mark.asyncio
async def test_a_failing_trust_check_fences_the_job_and_still_delivers_the_message() -> None:
    router = dispatch_router()
    router._is_sender_admitted = AsyncMock(return_value=True)
    router._resolver.is_untrusted_event_sender = AsyncMock(side_effect=RuntimeError("store down"))

    with patch(f"{PIPELINE}.dispatch_cron_event_for_inbound_message", new=AsyncMock()) as dispatch:
        await run_dispatch(router, inbound_msg("deploy now"))

    dispatch.assert_awaited_once_with("deploy now", "telegram", "", untrusted=True)
    assert len(gate_submissions(router)) == 1, "an error in the check must not end the dispatch before the gate"


@pytest.mark.asyncio
async def test_a_failing_owner_check_denies_the_delegation_but_not_the_message() -> None:
    router = dispatch_router()
    del router._check_admin_permission  # the real check, asking a pairing store that raises

    with patch(f"{PIPELINE}.is_admin_sender", new=AsyncMock(side_effect=RuntimeError("store down"))):
        await run_dispatch(router, inbound_msg("/delegate summarise the report"))

    router._handle_delegation_inbound.assert_not_awaited()
    assert len(gate_submissions(router)) == 1, "an error in the check must not end the dispatch before the gate"
