"""What one message from the session gate goes through around the agent's run: risk gate, agent-route alias, reactions,
the error path, and the exits that must always acknowledge the journal and free the gate.

Runs the real ``AgentRouter._handle_merged`` with the preparation, the execution and the message effects replaced by
recorders (see ``turn_pipeline_testkit``), so what is pinned is the sequence of steps around the run.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.command_defs import CommandKind
from app.channels.routing.commands import parse_topic_args
from app.channels.routing.placeholder_strategy import DeferredPlaceholder
from app.channels.routing.router_models import ReactionPolicy, _AgentTurnScratch
from app.channels.types import ReactionLevel
from app.channels.types.topics import METADATA_ROUTE_AGENT_KEY

from .turn_pipeline_testkit import (
    TURN,
    attach_journal,
    prepared_message,
    shown_reactions,
    tag_enricher_async,
    turn_msg,
    turn_router,
)

# --- risk gate and agent alias ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_held_message_runs_no_turn_and_acknowledges_the_journal() -> None:
    router = turn_router()
    journal = attach_journal(router)

    with patch(f"{TURN}.hold_risky_inbound", new=AsyncMock(return_value=True)) as hold:
        await router._handle_merged(turn_msg("a secret"))

    hold.assert_awaited_once()
    assert hold.await_args.args[2] == "a secret"
    router._prepare_execution_context.assert_not_awaited()
    journal.acknowledge.assert_called_once_with(journal.write.call_args.args[0].id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("content", "resume_value"), [("approve", {"type": "approve"}), ("", None)])
async def test_the_risk_gate_screens_typed_text_only(content: str, resume_value: dict[str, object] | None) -> None:
    router = turn_router()

    with patch(f"{TURN}.hold_risky_inbound", new=AsyncMock(return_value=True)) as hold:
        await router._handle_merged(turn_msg(content, resume_value=resume_value))

    hold.assert_not_awaited()
    router._prepare_execution_context.assert_awaited_once()


def _agent_route(raw_args: str, *, agent_id: str | None = "claude") -> SimpleNamespace:
    command_def = SimpleNamespace(kind=CommandKind.AGENT_ROUTE, agent_id=agent_id, name="alias")
    return SimpleNamespace(command_def=command_def, raw_args=raw_args)


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_id", "routed_to"), [("claude", "claude"), (None, "alias")])
async def test_an_agent_alias_with_a_request_runs_the_request_on_that_agent(agent_id: str | None, routed_to: str) -> None:
    router = turn_router()
    router._registry = MagicMock(resolve=MagicMock(return_value=_agent_route("do the thing", agent_id=agent_id)))

    await router._handle_merged(turn_msg("/claude do the thing"))

    prepared = prepared_message(router)
    assert prepared.content == "do the thing"
    assert prepared.metadata[METADATA_ROUTE_AGENT_KEY] == routed_to


@pytest.mark.asyncio
async def test_an_agent_alias_alone_binds_the_chat_to_that_agent_and_runs_no_turn() -> None:
    router = turn_router()
    router._registry = MagicMock(resolve=MagicMock(return_value=_agent_route("")))
    router._handle_topic_command = AsyncMock()
    journal = attach_journal(router)

    with patch(f"{TURN}.set_correlation_context") as correlation:
        await router._handle_merged(turn_msg("/claude"))
        await asyncio.sleep(0)

    router._handle_topic_command.assert_awaited_once()
    assert router._handle_topic_command.await_args.args[1] == parse_topic_args("bind", "claude")
    correlation.assert_called_once_with(None)
    router._prepare_execution_context.assert_not_awaited()
    journal.acknowledge.assert_called_once_with(journal.write.call_args.args[0].id)


@pytest.mark.asyncio
async def test_a_command_that_is_not_an_agent_alias_is_left_as_it_is() -> None:
    router = turn_router()
    resolved = _agent_route("whatever")
    resolved.command_def.kind = CommandKind.SYSTEM
    router._registry = MagicMock(resolve=MagicMock(return_value=resolved))

    await router._handle_merged(turn_msg("/status now"))

    assert prepared_message(router).content == "/status now"
    assert METADATA_ROUTE_AGENT_KEY not in prepared_message(router).metadata


# --- the run ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_completed_turn_is_marked_then_shows_the_completion_reaction() -> None:
    router = turn_router()
    journal = attach_journal(router)
    policy = router._reaction_policy

    async def finish(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.completed = True

    router._execute_prepared_context = AsyncMock(side_effect=finish)
    inbound = turn_msg()

    await router._handle_merged(inbound)

    assert shown_reactions(router) == [
        ("telegram", "chat-1", "m1", policy.processing_emoji),
        ("telegram", "chat-1", "m1", ""),
        ("telegram", "chat-1", "m1", policy.completion_emoji),
    ]
    router._retire_open_approval.assert_awaited_once()
    assert router._execute_prepared_context.await_args.kwargs == {"is_resume": False, "inbound_had_voice": False}
    router._fx.send_error_reply.assert_not_awaited()
    journal.acknowledge.assert_called_once()
    router._gate.on_task_complete.assert_called_once()
    assert router._gate.on_task_complete.call_args.args[0].channel == "telegram"


@pytest.mark.asyncio
async def test_a_turn_that_did_not_complete_has_its_mark_taken_off_and_gets_no_completion_reaction() -> None:
    router = turn_router()
    policy = router._reaction_policy

    await router._handle_merged(turn_msg())

    assert shown_reactions(router) == [
        ("telegram", "chat-1", "m1", policy.processing_emoji),
        ("telegram", "chat-1", "m1", ""),
    ]


@pytest.mark.asyncio
async def test_a_resumed_run_retires_no_approval() -> None:
    router = turn_router()

    await router._handle_merged(turn_msg("approve", resume_value={"type": "approve"}))

    router._retire_open_approval.assert_not_awaited()
    assert router._execute_prepared_context.await_args.kwargs["is_resume"] is True


@pytest.mark.asyncio
async def test_reactions_follow_the_policy() -> None:
    router = turn_router()
    router.set_reaction_policy(ReactionPolicy(level=ReactionLevel.OFF))

    async def finish(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.completed = True

    router._execute_prepared_context = AsyncMock(side_effect=finish)

    await router._handle_merged(turn_msg())

    router._fx.set_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_message_without_a_platform_id_gets_no_reaction() -> None:
    router = turn_router()

    async def finish(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.completed = True

    router._execute_prepared_context = AsyncMock(side_effect=finish)

    await router._handle_merged(turn_msg(message_id=""))

    router._fx.set_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_turn_that_cannot_be_prepared_ends_quietly_and_still_frees_the_gate() -> None:
    router = turn_router()
    journal = attach_journal(router)
    router._prepare_execution_context = AsyncMock(return_value=None)

    await router._handle_merged(turn_msg())

    router._execute_prepared_context.assert_not_awaited()
    router._fx.set_reaction.assert_not_awaited()
    router._fx.send_error_reply.assert_not_awaited()
    journal.acknowledge.assert_called_once()
    router._gate.on_task_complete.assert_called_once()


# --- the error path --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failing_run_is_reported_to_the_chat_with_the_message_the_run_used() -> None:
    router = turn_router(exec_content="policy output")
    journal = attach_journal(router)
    router._execute_prepared_context = AsyncMock(side_effect=RuntimeError("boom"))

    await router._handle_merged(turn_msg("typed text"))

    router._fx.send_error_reply.assert_awaited_once()
    reported, friendly = router._fx.send_error_reply.await_args.args
    assert reported.content == "policy output"
    assert "[ref:" in friendly
    assert shown_reactions(router) == [
        ("telegram", "chat-1", "m1", router._reaction_policy.processing_emoji),
        ("telegram", "chat-1", "m1", ""),
        ("telegram", "chat-1", "m1", router._reaction_policy.failure_emoji),
    ]
    journal.acknowledge.assert_called_once()
    router._gate.on_task_complete.assert_called_once()


@pytest.mark.asyncio
async def test_a_failure_before_the_chat_is_known_reports_to_the_enriched_message() -> None:
    router = turn_router()
    router._prepare_execution_context = AsyncMock(side_effect=RuntimeError("no chat"))

    with (
        patch(f"{TURN}.has_image_attachment_fn", return_value=True),
        patch(f"{TURN}.enrich_image_inbound", side_effect=tag_enricher_async("image")),
    ):
        await router._handle_merged(turn_msg("look"))

    reported, _ = router._fx.send_error_reply.await_args.args
    assert reported.content == "look+image"
    # No chat is known yet and nothing was marked: the failure is still shown on the message, and nothing is taken off.
    assert shown_reactions(router) == [("telegram", "", "m1", router._reaction_policy.failure_emoji)]
    router._fx.cleanup_placeholder.assert_not_awaited()
    router._gate.on_task_complete.assert_called_once()


@pytest.mark.asyncio
async def test_a_failing_turn_sends_the_error_text_before_it_shows_the_failure_reaction() -> None:
    router = turn_router()
    router._execute_prepared_context = AsyncMock(side_effect=RuntimeError("boom"))
    order: list[str] = []
    router._fx.send_error_reply.side_effect = lambda *_: order.append("text")
    router._fx.set_reaction.side_effect = lambda *args: order.append(f"reaction:{args[3] or 'off'}")

    await router._handle_merged(turn_msg())

    policy = router._reaction_policy
    mark = f"reaction:{policy.processing_emoji}"
    assert order.count(mark) == 1
    assert order.index(mark) < order.index("reaction:off")
    assert order.index("text") < order.index("reaction:off")
    assert order[-2:] == ["reaction:off", f"reaction:{policy.failure_emoji}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("chat_id", "cleaned"), [("chat-1", True), ("", False)])
async def test_a_placeholder_already_sent_is_turned_into_the_error_text(chat_id: str, cleaned: bool) -> None:
    router = turn_router(prepared_chat_id=chat_id)
    placeholder = DeferredPlaceholder()
    placeholder.start(AsyncMock(return_value="ph-1"))
    await placeholder.mark_activity()

    async def fail(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.deferred_placeholder = placeholder
        raise RuntimeError("boom")

    router._execute_prepared_context = AsyncMock(side_effect=fail)

    await router._handle_merged(turn_msg())
    await placeholder.cancel()

    if cleaned:
        router._fx.cleanup_placeholder.assert_awaited_once()
        assert router._fx.cleanup_placeholder.await_args.args[:3] == ("telegram", "chat-1", "ph-1")
        assert router._fx.cleanup_placeholder.await_args.args[3] == router._fx.send_error_reply.await_args.args[1]
    else:
        router._fx.cleanup_placeholder.assert_not_awaited()
    router._fx.send_error_reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failure_does_not_reach_the_consume_loop() -> None:
    router = turn_router()
    router._execute_prepared_context = AsyncMock(side_effect=RuntimeError("boom"))

    await router._handle_merged(turn_msg())  # does not raise
