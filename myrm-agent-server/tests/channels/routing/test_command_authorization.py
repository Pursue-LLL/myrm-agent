"""Command authorization: built-in system commands are owner-only unless they stay inside the sender's own conversation.

The router dispatches commands before the DM policy and the sender's identity are resolved, so a command that
reaches the owner's sandbox (memory, kanban, topic bindings, background runs, delegation) has to be refused to
every other sender, whatever the DM policy admitted.
"""

from __future__ import annotations

import asyncio
import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.pairing import PairingRole, PairingStatus
from app.channels.routing.command_defs import SYSTEM_COMMANDS, CommandAction, CommandDef, CommandKind
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage

_OWNER = (PairingStatus.ACTIVE, PairingRole.ADMIN, None)
_MEMBER = (PairingStatus.ACTIVE, PairingRole.MEMBER, None)

# Commands any sender may run: each one only touches the sender's own conversation and costs at most one turn.
_ANY_SENDER_COMMANDS = {
    "/stop": "_cancel_active_task",
    "/new": "_handle_new_session",
    "/compact": "_handle_compact",
    "/retry": "_handle_retry",
    "/undo": "_handle_undo",
    "/personality list": "_handle_personality_command",
    "/steer go on": "_handle_steer_command",
    "/queue next job": "_handle_queue_command",
    "/status": "_handle_status_command",
    "/quota": "_handle_quota_command",
    "/help": "_handle_help_command",
}

# Commands that act on the owner's sandbox: settings, topic bindings, goals, memory, kanban, skills, background runs.
_OWNER_ONLY_COMMANDS = {
    "/yolo on": "_handle_yolo_command",
    "/bind agent-1": "_handle_topic_command",
    "/unbind": "_handle_topic_command",
    "/topic": "_handle_topic_command",
    "/draft approve 3f9a1c2e": "_handle_draft_command",
    "/goal ship the report": "_handle_goal_command",
    "/subgoal write the intro": "_handle_subgoal_command",
    "/background research rivals": "_handle_background_command",
    "/bg research rivals": "_handle_background_command",
    "/kanban list": "_handle_kanban_command",
    "/kb list": "_handle_kanban_command",
    "/memory": "_handle_memory_command",
    "/learn https://example.com/skill": "_handle_learn_command",
    "/handoff telegram": "_handle_handoff_command",
}


def _make_router(detail: tuple[PairingStatus, PairingRole, int | None] | None) -> tuple[AgentRouter, MagicMock]:
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    pairing = MagicMock()
    pairing.get_pairing_detail = AsyncMock(return_value=detail)
    router = AgentRouter(bus=bus, pairing_store=pairing, agent_executor=MagicMock())
    return router, bus


def _msg(content: str, *, is_group: bool = False) -> InboundMessage:
    return InboundMessage(channel="test", sender_id="sender-1", chat_id="chat-1", content=content, is_group=is_group)


async def _dispatch(router: AgentRouter, msg: InboundMessage) -> bool:
    resolved = router._registry.resolve(msg.content)
    assert resolved is not None, msg.content
    handled = await router._dispatch_resolved(msg, resolved)
    await asyncio.sleep(0)  # let the handler task the router spawned start
    return handled


def _replace_handler(router: AgentRouter, name: str) -> AsyncMock:
    handler = AsyncMock()
    setattr(router, name, handler)
    return handler


class TestCommandCatalog:
    def test_only_commands_confined_to_the_senders_own_conversation_are_open_to_any_sender(self) -> None:
        open_commands = {cmd.name for cmd in SYSTEM_COMMANDS if cmd.kind is CommandKind.SYSTEM and cmd.any_sender}

        assert open_commands == {
            "stop",
            "new",
            "compact",
            "retry",
            "undo",
            "personality",
            "steer",
            "queue",
            "status",
            "quota",
            "help",
        }

    def test_skill_and_agent_commands_run_through_the_per_turn_pipeline_and_are_never_owner_only(self) -> None:
        skill = CommandDef(name="memo", description="x", kind=CommandKind.SKILL)
        agent = CommandDef(name="research", description="x", kind=CommandKind.AGENT_ROUTE)

        assert skill.owner_only is False
        assert agent.owner_only is False

    def test_a_system_command_is_owner_only_unless_it_opts_in(self) -> None:
        assert CommandDef(name="x", description="x", action=CommandAction.GOAL).owner_only is True
        assert CommandDef(name="x", description="x", action=CommandAction.STATUS, any_sender=True).owner_only is False


class TestSystemCommandGate:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("is_group", [False, True], ids=["dm", "group"])
    @pytest.mark.parametrize("detail", [None, _MEMBER], ids=["unpaired", "member"])
    @pytest.mark.parametrize(("text", "handler_name"), list(_OWNER_ONLY_COMMANDS.items()), ids=list(_OWNER_ONLY_COMMANDS))
    async def test_owner_only_commands_are_refused_to_everyone_else(
        self,
        text: str,
        handler_name: str,
        detail: tuple[PairingStatus, PairingRole, int | None] | None,
        is_group: bool,
    ) -> None:
        router, bus = _make_router(detail)
        handler = _replace_handler(router, handler_name)

        assert await _dispatch(router, _msg(text, is_group=is_group)) is True

        handler.assert_not_called()
        bus.publish_outbound.assert_called_once()
        reply = bus.publish_outbound.call_args[0][0]
        assert "Permission denied" in reply.content
        assert f"`/{router._registry.resolve(text).command_def.name}`" in reply.content

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("text", "handler_name"), list(_OWNER_ONLY_COMMANDS.items()), ids=list(_OWNER_ONLY_COMMANDS))
    async def test_the_owner_reaches_every_owner_only_command(self, text: str, handler_name: str) -> None:
        router, bus = _make_router(_OWNER)
        handler = _replace_handler(router, handler_name)

        assert await _dispatch(router, _msg(text)) is True

        handler.assert_called_once()
        bus.publish_outbound.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("detail", [None, _MEMBER], ids=["unpaired", "member"])
    @pytest.mark.parametrize(("text", "handler_name"), list(_ANY_SENDER_COMMANDS.items()), ids=list(_ANY_SENDER_COMMANDS))
    async def test_conversation_scoped_commands_stay_open_to_any_sender(
        self,
        text: str,
        handler_name: str,
        detail: tuple[PairingStatus, PairingRole, int | None] | None,
    ) -> None:
        router, bus = _make_router(detail)
        handler = _replace_handler(router, handler_name)

        assert await _dispatch(router, _msg(text)) is True

        handler.assert_called_once()
        bus.publish_outbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_refused_btw_is_not_picked_up_by_the_delegation_prefix(self) -> None:
        """``/btw`` is also a delegation prefix, so refusing it here is what keeps strangers out of that path."""
        router, bus = _make_router(None)

        assert await _dispatch(router, _msg("/btw what is this")) is True

        assert "Permission denied" in bus.publish_outbound.call_args[0][0].content


class TestHelpListing:
    def test_help_lists_only_the_commands_the_sender_may_run(self) -> None:
        router, _ = _make_router(None)

        text = "\n".join(router._registry.help_lines(owner=False))

        assert "`/stop" in text
        assert "`/quota" in text
        assert "`/goal" not in text
        assert "`/memory" not in text
        assert "`/background" not in text

    def test_help_lists_everything_to_the_owner(self) -> None:
        router, _ = _make_router(_OWNER)

        text = "\n".join(router._registry.help_lines(owner=True))

        assert "`/stop" in text
        assert "`/goal" in text
        assert "`/memory" in text

    @pytest.mark.asyncio
    async def test_the_help_reply_follows_the_senders_role(self) -> None:
        stranger, stranger_bus = _make_router(None)
        owner, owner_bus = _make_router(_OWNER)

        await stranger._handle_help_command(_msg("/help"))
        await owner._handle_help_command(_msg("/help"))

        assert "`/goal" not in stranger_bus.publish_outbound.call_args[0][0].content
        assert "`/goal" in owner_bus.publish_outbound.call_args[0][0].content


def _delegation_router(detail: tuple[PairingStatus, PairingRole, int | None] | None) -> tuple[AgentRouter, MagicMock]:
    router, bus = _make_router(detail)
    router._gate = MagicMock()
    router._handle_delegation_inbound = AsyncMock(return_value=True)
    return router, bus


async def _consume(router: AgentRouter, bus: MagicMock, msg: InboundMessage) -> None:
    pending = [msg]

    async def next_inbound() -> InboundMessage:
        if pending:
            return pending.pop()
        raise asyncio.CancelledError

    bus.consume_inbound = AsyncMock(side_effect=next_inbound)
    router._running = True
    await router._consume_loop()
    await asyncio.sleep(0)


class TestDelegationGate:
    """Delegated runs and their in-flight steering skip the per-turn identity pipeline, so they are owner-only."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("detail", [None, _MEMBER], ids=["unpaired", "member"])
    @pytest.mark.parametrize(
        "text",
        [
            "/delegate research the market",
            "请深度调研 2026 年行业动向，然后分析竞品，最后生成PPT和报表，明早给我",
        ],
        ids=["explicit", "natural-language"],
    )
    async def test_a_stranger_cannot_delegate_a_task(
        self, text: str, detail: tuple[PairingStatus, PairingRole, int | None] | None
    ) -> None:
        router, bus = _delegation_router(detail)

        await _consume(router, bus, _msg(text))

        router._handle_delegation_inbound.assert_not_called()
        router._gate.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_the_owner_can_delegate_a_task(self) -> None:
        router, bus = _delegation_router(_OWNER)

        await _consume(router, bus, _msg("/delegate research the market"))

        router._handle_delegation_inbound.assert_awaited_once()
        assert router._handle_delegation_inbound.await_args.args[1] == "research the market"
        router._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("detail", "steered"), [(None, False), (_MEMBER, False), (_OWNER, True)], ids=["unpaired", "member", "owner"]
    )
    async def test_only_the_owner_can_steer_a_running_delegation(
        self, detail: tuple[PairingStatus, PairingRole, int | None] | None, steered: bool
    ) -> None:
        router, bus = _delegation_router(detail)
        router._delegation_coordinator.find_active_task = MagicMock(return_value=SimpleNamespace(task_id="task-1"))
        router._delegation_coordinator.inject_steering = MagicMock(return_value=True)

        await _consume(router, bus, dataclasses.replace(_msg("also add the Q3 figures"), is_group=True))

        assert router._delegation_coordinator.inject_steering.called is steered
        assert router._gate.submit.called is not steered
