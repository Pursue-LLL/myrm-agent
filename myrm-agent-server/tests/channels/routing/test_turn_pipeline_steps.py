"""What one message from the session gate goes through before and after the agent runs it.

Runs the real ``AgentRouter._handle_merged`` with the preparation, the execution and the message effects replaced by
recorders, so what is pinned is the sequence of steps around the run: journal, session state, enrichment, risk gate,
agent-route alias, reactions, the error path, and the exits that must always acknowledge the journal and free the gate.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.command_defs import CommandKind
from app.channels.routing.commands import parse_topic_args
from app.channels.routing.placeholder_strategy import DeferredPlaceholder
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.router_models import ReactionPolicy, _AgentTurnScratch
from app.channels.types import InboundMessage, ReactionLevel
from app.channels.types.topics import METADATA_ROUTE_AGENT_KEY

from .risk_gate_testkit import make_router

_TURN = "app.channels.routing.pipeline.turn"
_STATE_KEY = routing_state_key("telegram", "chat-1", None)


def _msg(
    content: str = "hello",
    *,
    message_id: str = "m1",
    metadata: dict[str, object] | None = None,
    resume_value: dict[str, object] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="chat-1",
        content=content,
        message_id=message_id,
        metadata=metadata or {},
        resume_value=resume_value,
    )


def _router(*, prepared_chat_id: str = "chat-1", exec_content: str | None = None) -> AgentRouter:
    """A router whose run is recorded: the preparation hands back a context, the execution does nothing."""
    router = make_router()
    router._gate = MagicMock()
    router._fx = MagicMock(
        ack_reaction=AsyncMock(),
        completion_reaction=AsyncMock(),
        cleanup_placeholder=AsyncMock(),
        send_error_reply=AsyncMock(),
    )

    async def prepare(inbound: InboundMessage) -> SimpleNamespace:
        exec_msg = inbound if exec_content is None else dataclasses.replace(inbound, content=exec_content)
        return SimpleNamespace(chat_id=prepared_chat_id, exec_msg=exec_msg)

    router._prepare_execution_context = AsyncMock(side_effect=prepare)
    router._execute_prepared_context = AsyncMock()
    router._retire_open_approval = AsyncMock()
    return router


def _prepared(router: AgentRouter) -> InboundMessage:
    prepared: InboundMessage = router._prepare_execution_context.await_args.args[0]
    return prepared


def _journal(router: AgentRouter) -> MagicMock:
    journal = MagicMock()
    router.set_inbound_journal(journal)
    return journal


def _tag(name: str) -> Callable[..., InboundMessage]:
    """An enricher that leaves a mark on the content, to show the order the steps ran in."""

    def enrich(inbound: InboundMessage, *_: object, **__: object) -> InboundMessage:
        return dataclasses.replace(inbound, content=f"{inbound.content}+{name}")

    return enrich


def _tag_async(name: str) -> Callable[..., Awaitable[InboundMessage]]:
    sync = _tag(name)

    async def enrich(inbound: InboundMessage, *args: object, **kwargs: object) -> InboundMessage:
        return sync(inbound, *args, **kwargs)

    return enrich


# --- journal ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_fresh_message_is_journaled_and_acknowledged_when_the_turn_is_over() -> None:
    router = _router()
    journal = _journal(router)

    await router._handle_merged(_msg())

    journal.write.assert_called_once()
    journal.acknowledge.assert_called_once_with(journal.write.call_args.args[0].id)


@pytest.mark.asyncio
async def test_a_replayed_message_is_not_journaled_again_and_acknowledges_its_own_entry() -> None:
    router = _router()
    journal = _journal(router)

    await router._handle_merged(_msg(metadata={"is_recovery": True, "recovery_entry_id": "entry-7"}))

    journal.write.assert_not_called()
    journal.acknowledge.assert_called_once_with("entry-7")


@pytest.mark.asyncio
async def test_a_replayed_message_without_an_entry_id_touches_the_journal_not_at_all() -> None:
    router = _router()
    journal = _journal(router)

    await router._handle_merged(_msg(metadata={"is_recovery": True}))

    journal.write.assert_not_called()
    journal.acknowledge.assert_not_called()


# --- session state ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("timeout", "expected"), [(3600, 3600), (None, None), (0, None)])
async def test_a_running_yolo_window_rides_on_the_message(timeout: int | None, expected: int | None) -> None:
    router = _router()
    enabled_at = time.time() - 5
    router._session_yolo[_STATE_KEY] = (enabled_at, timeout)

    await router._handle_merged(_msg())

    assert _prepared(router).metadata["yolo_state"] == (enabled_at, expected)
    assert _STATE_KEY in router._session_yolo


@pytest.mark.asyncio
async def test_an_expired_yolo_window_is_dropped_and_not_applied() -> None:
    router = _router()
    router._session_yolo[_STATE_KEY] = (time.time() - 100, 10)

    await router._handle_merged(_msg())

    assert "yolo_state" not in _prepared(router).metadata
    assert _STATE_KEY not in router._session_yolo


@pytest.mark.asyncio
async def test_the_personality_of_the_session_rides_on_the_message() -> None:
    router = _router()
    router._session_personality[_STATE_KEY] = "pirate"

    await router._handle_merged(_msg())

    assert _prepared(router).metadata["personality_style"] == "pirate"


@pytest.mark.asyncio
async def test_session_state_of_another_thread_is_not_applied() -> None:
    router = _router()
    other_thread = routing_state_key("telegram", "chat-1", "th-9")
    router._session_yolo[other_thread] = (time.time(), None)
    router._session_personality[other_thread] = "pirate"

    await router._handle_merged(_msg())

    assert {"yolo_state", "personality_style"}.isdisjoint(_prepared(router).metadata)


# --- attachments -----------------------------------------------------------------------------------------------------


_ENRICHERS = [
    pytest.param("has_video_attachment_fn", "enrich_video_inbound", False, id="video"),
    pytest.param("has_image_attachment_fn", "enrich_image_inbound", True, id="image"),
    pytest.param("has_contact_attachment", "enrich_contact_inbound", True, id="contact"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("has", "enrich", "is_async"), _ENRICHERS)
async def test_an_attachment_of_a_new_turn_is_enriched_into_the_message(has: str, enrich: str, is_async: bool) -> None:
    router = _router()
    make = _tag_async if is_async else _tag

    with (
        patch(f"{_TURN}.{has}", return_value=True),
        patch(f"{_TURN}.{enrich}", side_effect=make(enrich)) as enricher,
        patch(f"{_TURN}.has_video_with_audio", return_value=False),
    ):
        await router._handle_merged(_msg("see this"))

    enricher.assert_called_once()
    assert _prepared(router).content == f"see this+{enrich}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("has", "enrich", "is_async"), _ENRICHERS)
async def test_the_answer_to_an_approval_is_not_enriched(has: str, enrich: str, is_async: bool) -> None:
    router = _router()

    with patch(f"{_TURN}.{has}", return_value=True) as present, patch(f"{_TURN}.{enrich}") as enricher:
        await router._handle_merged(_msg("approve", resume_value={"type": "approve"}))

    present.assert_not_called()
    enricher.assert_not_called()
    assert _prepared(router).content == "approve"


@pytest.mark.asyncio
async def test_a_video_with_sound_gets_its_audio_transcribed_after_the_video_is_described() -> None:
    router = _router()

    with (
        patch(f"{_TURN}.has_video_attachment_fn", return_value=True),
        patch(f"{_TURN}.enrich_video_inbound", side_effect=_tag("video")),
        patch(f"{_TURN}.has_video_with_audio", return_value=True),
        patch(f"{_TURN}.transcribe_video_inbound", side_effect=_tag_async("video-audio")),
    ):
        await router._handle_merged(_msg("clip"))

    assert _prepared(router).content == "clip+video+video-audio"


@pytest.mark.asyncio
async def test_a_document_is_enriched_with_the_owners_extraction_setting() -> None:
    router = _router()
    enrich = AsyncMock(side_effect=_tag_async("document"))

    with (
        patch(f"{_TURN}.has_document_attachment", return_value=True),
        patch(f"{_TURN}.enrich_document_inbound", new=enrich),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=SimpleNamespace(personal_settings_dict={"k": 1})),
        ),
        patch("app.services.files.attachment_settings.should_extract_document_text", return_value=True) as should_extract,
    ):
        await router._handle_merged(_msg("report"))

    should_extract.assert_called_once_with({"k": 1})
    assert enrich.await_args.kwargs == {"extract_enabled": True}
    assert _prepared(router).content == "report+document"


@pytest.mark.asyncio
async def test_a_voice_message_is_transcribed_and_the_run_is_told_it_was_voice() -> None:
    router = _router()

    with (
        patch(f"{_TURN}.has_audio_attachment", return_value=True),
        patch(f"{_TURN}.transcribe_inbound", side_effect=_tag_async("voice")),
    ):
        await router._handle_merged(_msg("spoken"))

    assert _prepared(router).content == "spoken+voice"
    assert router._execute_prepared_context.await_args.kwargs == {"is_resume": False, "inbound_had_voice": True}


@pytest.mark.asyncio
async def test_the_answer_to_an_approval_is_not_checked_for_voice() -> None:
    router = _router()

    with patch(f"{_TURN}.has_audio_attachment", return_value=True) as present, patch(f"{_TURN}.transcribe_inbound") as transcribe:
        await router._handle_merged(_msg("approve", resume_value={"type": "approve"}))

    present.assert_not_called()
    transcribe.assert_not_called()
    assert router._execute_prepared_context.await_args.kwargs == {"is_resume": True, "inbound_had_voice": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
async def test_a_sticker_is_described_with_or_without_a_resume(resume: bool) -> None:
    router = _router()
    router._sticker_vision = MagicMock()
    resume_value = {"type": "approve"} if resume else None

    with patch(f"{_TURN}.describe_sticker_inbound", side_effect=_tag_async("sticker")):
        await router._handle_merged(_msg("sticker", metadata={"is_sticker": True}, resume_value=resume_value))

    assert _prepared(router).content == "sticker+sticker"


@pytest.mark.asyncio
async def test_a_sticker_is_left_alone_without_a_vision_service() -> None:
    router = _router()
    router._sticker_vision = None

    with patch(f"{_TURN}.describe_sticker_inbound") as describe:
        await router._handle_merged(_msg("sticker", metadata={"is_sticker": True}))

    describe.assert_not_called()


@pytest.mark.asyncio
async def test_the_enrichers_run_in_a_fixed_order() -> None:
    router = _router()
    router._sticker_vision = MagicMock()

    with (
        patch(f"{_TURN}.has_audio_attachment", return_value=True),
        patch(f"{_TURN}.transcribe_inbound", side_effect=_tag_async("voice")),
        patch(f"{_TURN}.describe_sticker_inbound", side_effect=_tag_async("sticker")),
        patch(f"{_TURN}.has_video_attachment_fn", return_value=True),
        patch(f"{_TURN}.enrich_video_inbound", side_effect=_tag("video")),
        patch(f"{_TURN}.has_video_with_audio", return_value=False),
        patch(f"{_TURN}.has_image_attachment_fn", return_value=True),
        patch(f"{_TURN}.enrich_image_inbound", side_effect=_tag_async("image")),
        patch(f"{_TURN}.has_contact_attachment", return_value=True),
        patch(f"{_TURN}.enrich_contact_inbound", side_effect=_tag_async("contact")),
    ):
        await router._handle_merged(_msg("x", metadata={"is_sticker": True}))

    assert _prepared(router).content == "x+voice+sticker+video+image+contact"


# --- risk gate and agent alias ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_held_message_runs_no_turn_and_acknowledges_the_journal() -> None:
    router = _router()
    journal = _journal(router)

    with patch(f"{_TURN}.hold_risky_inbound", new=AsyncMock(return_value=True)) as hold:
        await router._handle_merged(_msg("a secret"))

    hold.assert_awaited_once()
    assert hold.await_args.args[2] == "a secret"
    router._prepare_execution_context.assert_not_awaited()
    journal.acknowledge.assert_called_once_with(journal.write.call_args.args[0].id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("content", "resume_value"), [("approve", {"type": "approve"}), ("", None)])
async def test_the_risk_gate_screens_typed_text_only(content: str, resume_value: dict[str, object] | None) -> None:
    router = _router()

    with patch(f"{_TURN}.hold_risky_inbound", new=AsyncMock(return_value=True)) as hold:
        await router._handle_merged(_msg(content, resume_value=resume_value))

    hold.assert_not_awaited()
    router._prepare_execution_context.assert_awaited_once()


def _agent_route(raw_args: str, *, agent_id: str | None = "claude") -> SimpleNamespace:
    command_def = SimpleNamespace(kind=CommandKind.AGENT_ROUTE, agent_id=agent_id, name="alias")
    return SimpleNamespace(command_def=command_def, raw_args=raw_args)


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_id", "routed_to"), [("claude", "claude"), (None, "alias")])
async def test_an_agent_alias_with_a_request_runs_the_request_on_that_agent(agent_id: str | None, routed_to: str) -> None:
    router = _router()
    router._registry = MagicMock(resolve=MagicMock(return_value=_agent_route("do the thing", agent_id=agent_id)))

    await router._handle_merged(_msg("/claude do the thing"))

    prepared = _prepared(router)
    assert prepared.content == "do the thing"
    assert prepared.metadata[METADATA_ROUTE_AGENT_KEY] == routed_to


@pytest.mark.asyncio
async def test_an_agent_alias_alone_binds_the_chat_to_that_agent_and_runs_no_turn() -> None:
    router = _router()
    router._registry = MagicMock(resolve=MagicMock(return_value=_agent_route("")))
    router._handle_topic_command = AsyncMock()
    journal = _journal(router)

    with patch(f"{_TURN}.set_correlation_context") as correlation:
        await router._handle_merged(_msg("/claude"))
        await asyncio.sleep(0)

    router._handle_topic_command.assert_awaited_once()
    assert router._handle_topic_command.await_args.args[1] == parse_topic_args("bind", "claude")
    correlation.assert_called_once_with(None)
    router._prepare_execution_context.assert_not_awaited()
    journal.acknowledge.assert_called_once_with(journal.write.call_args.args[0].id)


@pytest.mark.asyncio
async def test_a_command_that_is_not_an_agent_alias_is_left_as_it_is() -> None:
    router = _router()
    resolved = _agent_route("whatever")
    resolved.command_def.kind = CommandKind.SYSTEM
    router._registry = MagicMock(resolve=MagicMock(return_value=resolved))

    await router._handle_merged(_msg("/status now"))

    assert _prepared(router).content == "/status now"
    assert METADATA_ROUTE_AGENT_KEY not in _prepared(router).metadata


# --- the run ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_completed_turn_is_acknowledged_and_completed_with_reactions() -> None:
    router = _router()
    journal = _journal(router)
    policy = router._reaction_policy

    async def finish(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.completed = True

    router._execute_prepared_context = AsyncMock(side_effect=finish)
    inbound = _msg()

    await router._handle_merged(inbound)

    router._fx.ack_reaction.assert_awaited_once_with("telegram", "chat-1", "m1", emoji=policy.processing_emoji)
    router._fx.completion_reaction.assert_awaited_once_with(
        "telegram",
        "chat-1",
        "m1",
        success=True,
        success_emoji=policy.completion_emoji,
        failure_emoji=policy.failure_emoji,
        had_ack=True,
    )
    router._retire_open_approval.assert_awaited_once()
    assert router._execute_prepared_context.await_args.kwargs == {"is_resume": False, "inbound_had_voice": False}
    router._fx.send_error_reply.assert_not_awaited()
    journal.acknowledge.assert_called_once()
    router._gate.on_task_complete.assert_called_once()
    assert router._gate.on_task_complete.call_args.args[0].channel == "telegram"


@pytest.mark.asyncio
async def test_a_turn_that_did_not_complete_gets_no_completion_reaction() -> None:
    router = _router()

    await router._handle_merged(_msg())

    router._fx.ack_reaction.assert_awaited_once()
    router._fx.completion_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_resumed_run_retires_no_approval() -> None:
    router = _router()

    await router._handle_merged(_msg("approve", resume_value={"type": "approve"}))

    router._retire_open_approval.assert_not_awaited()
    assert router._execute_prepared_context.await_args.kwargs["is_resume"] is True


@pytest.mark.asyncio
async def test_reactions_follow_the_policy() -> None:
    router = _router()
    router.set_reaction_policy(ReactionPolicy(level=ReactionLevel.OFF))

    async def finish(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.completed = True

    router._execute_prepared_context = AsyncMock(side_effect=finish)

    await router._handle_merged(_msg())

    router._fx.ack_reaction.assert_not_awaited()
    router._fx.completion_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_message_without_a_platform_id_gets_no_completion_reaction() -> None:
    router = _router()

    async def finish(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.completed = True

    router._execute_prepared_context = AsyncMock(side_effect=finish)

    await router._handle_merged(_msg(message_id=""))

    router._fx.completion_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_turn_that_cannot_be_prepared_ends_quietly_and_still_frees_the_gate() -> None:
    router = _router()
    journal = _journal(router)
    router._prepare_execution_context = AsyncMock(return_value=None)

    await router._handle_merged(_msg())

    router._execute_prepared_context.assert_not_awaited()
    router._fx.ack_reaction.assert_not_awaited()
    router._fx.send_error_reply.assert_not_awaited()
    journal.acknowledge.assert_called_once()
    router._gate.on_task_complete.assert_called_once()


# --- the error path --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failing_run_is_reported_to_the_chat_with_the_message_the_run_used() -> None:
    router = _router(exec_content="policy output")
    journal = _journal(router)
    router._execute_prepared_context = AsyncMock(side_effect=RuntimeError("boom"))

    await router._handle_merged(_msg("typed text"))

    router._fx.send_error_reply.assert_awaited_once()
    reported, friendly = router._fx.send_error_reply.await_args.args
    assert reported.content == "policy output"
    assert "[ref:" in friendly
    router._fx.completion_reaction.assert_awaited_once()
    assert router._fx.completion_reaction.await_args.args == ("telegram", "chat-1", "m1")
    assert router._fx.completion_reaction.await_args.kwargs["success"] is False
    assert router._fx.completion_reaction.await_args.kwargs["had_ack"] is True
    journal.acknowledge.assert_called_once()
    router._gate.on_task_complete.assert_called_once()


@pytest.mark.asyncio
async def test_a_failure_before_the_chat_is_known_reports_to_the_enriched_message() -> None:
    router = _router()
    router._prepare_execution_context = AsyncMock(side_effect=RuntimeError("no chat"))

    with (
        patch(f"{_TURN}.has_image_attachment_fn", return_value=True),
        patch(f"{_TURN}.enrich_image_inbound", side_effect=_tag_async("image")),
    ):
        await router._handle_merged(_msg("look"))

    reported, _ = router._fx.send_error_reply.await_args.args
    assert reported.content == "look+image"
    assert router._fx.completion_reaction.await_args.args == ("telegram", "", "m1")
    router._fx.cleanup_placeholder.assert_not_awaited()
    router._gate.on_task_complete.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("chat_id", "cleaned"), [("chat-1", True), ("", False)])
async def test_a_placeholder_already_sent_is_turned_into_the_error_text(chat_id: str, cleaned: bool) -> None:
    router = _router(prepared_chat_id=chat_id)
    placeholder = DeferredPlaceholder()
    placeholder.start(AsyncMock(return_value="ph-1"))
    await placeholder.mark_activity()

    async def fail(_ctx: object, scratch: _AgentTurnScratch, **_: object) -> None:
        scratch.deferred_placeholder = placeholder
        raise RuntimeError("boom")

    router._execute_prepared_context = AsyncMock(side_effect=fail)

    await router._handle_merged(_msg())
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
    router = _router()
    router._execute_prepared_context = AsyncMock(side_effect=RuntimeError("boom"))

    await router._handle_merged(_msg())  # does not raise
