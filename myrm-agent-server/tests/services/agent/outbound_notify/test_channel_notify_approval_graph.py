"""channel_notify_tool behind the shipped approval middleware on a real LangGraph agent.

The person approves a send knowing where it goes, and a call outside the configured destinations sends nothing:
1. The approval card shows the destination the model chose; approving delivers to that destination's recipient and to no
   other, whatever order the targets were configured in. Rejecting delivers nothing, and a YOLO session still waits.
2. A destination that is not configured, or none at all (the former channel/target shape included), is refused by the
   tool's schema; nothing reaches the gateway.

Only the gateway bus (the network edge) and the scripted model are fakes.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path

import myrm_agent_harness.agent.security.approval_flow as approval_flow
import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import (
    set_approval_session,
    set_approval_user_id,
    set_security_config,
    set_workspace_root,
)
from myrm_agent_harness.agent.middlewares.approval import get_approval_rate_limiter
from myrm_agent_harness.agent.middlewares.approval.batch_processor import register_security_reviewer
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import clear_all_session_loop_guards_for_tests
from myrm_agent_harness.agent.security.audit import reset_audit_log
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.types import PrivacyPolicy, SecurityConfig

from app.channels.types import OutboundMessage
from app.services.agent.outbound_notify import create_channel_notify_tool, create_notification_sender

_THREAD = {"configurable": {"thread_id": "t"}}

_TARGETS = (
    {"channel": "telegram", "recipient_id": "111", "label": "me"},
    {"channel": "telegram", "recipient_id": "222", "label": "work"},
    {"channel": "slack", "recipient_id": "C333", "label": "ops"},
)
_ONE_TARGET = ({"channel": "telegram", "recipient_id": "111", "label": "我"},)


class _FakeBus:
    """Records what the gateway would deliver."""

    def __init__(self) -> None:
        self.delivered: list[tuple[str, str, str]] = []

    async def send_now(self, msg: OutboundMessage) -> str:
        self.delivered.append((msg.channel, msg.recipient_id, msg.content))
        return "message-1"


class _CallsOnce(BaseChatModel):
    """Makes one channel_notify_tool call in its first turn, then answers."""

    tool_args: dict[str, object]
    served: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> _CallsOnce:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        if self.served == 0:
            reply = AIMessage(content="", tool_calls=[{"id": "c0", "name": "channel_notify_tool", "args": self.tool_args}])
        else:
            reply = AIMessage(content="done")
        self.served += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


@pytest.fixture
def bus(monkeypatch: pytest.MonkeyPatch) -> _FakeBus:
    """Stand in for the gateway module. Only this one entry is swapped: restoring a whole ``sys.modules`` snapshot would
    drop the modules the agent imports lazily (the metrics registry among them) and import them again, which registers
    their Prometheus metrics twice."""
    fake = _FakeBus()
    gateway_module = types.SimpleNamespace(channel_gateway=types.SimpleNamespace(bus=fake))
    monkeypatch.setitem(sys.modules, "app.core.channel_bridge", gateway_module)
    return fake


@pytest.fixture(autouse=True)
def _web_session(tmp_path: Path) -> Iterator[None]:
    approval_flow._allowlist = approval_flow.Allowlist()
    reset_taint_tracker()
    reset_audit_log()
    clear_all_session_denials_for_tests()
    clear_all_session_loop_guards_for_tests()
    get_approval_rate_limiter().reset(None)
    register_security_reviewer(None)
    set_security_config(SecurityConfig(yolo_mode_enabled=False, privacy_policy=PrivacyPolicy(enabled=False)))
    set_workspace_root(str(tmp_path))
    set_approval_session("web-session")
    set_approval_user_id("user-1")
    yield
    register_security_reviewer(None)
    reset_taint_tracker()


def _agent(raw_targets: tuple[dict[str, str], ...], args: dict[str, object]) -> CompiledStateGraph:
    created = create_notification_sender(raw_targets)
    assert created is not None
    sender, config = created
    return create_agent(
        _CallsOnce(tool_args=args),
        tools=[create_channel_notify_tool(sender, config)],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=InMemorySaver(),
    )


async def _start(agent: CompiledStateGraph) -> dict[str, object]:
    return await agent.ainvoke({"messages": [HumanMessage(content="go")]}, _THREAD)


async def _decide(agent: CompiledStateGraph, decision: str) -> dict[str, object]:
    return await agent.ainvoke(Command(resume={"decisions": [{"type": decision}]}), _THREAD)


def _card(paused: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    """The pending approval: its review flags and the arguments the person is shown."""
    assert "__interrupt__" in paused
    pending = paused["__interrupt__"][0].value
    return pending["reviewConfigs"][0], pending["actionRequests"][0]["args"]


def _tool_reply(state: dict[str, object]) -> str:
    replies = [message for message in state["messages"] if isinstance(message, ToolMessage)]
    return str(replies[-1].content)


# Each target is the one named, configured first, in the middle and last among the others.
_EVERY_POSITION_OF_EACH_CHOICE = [
    pytest.param(chosen, position, id=f"{_TARGETS[chosen]['label']}-configured-{position + 1}-of-{len(_TARGETS)}")
    for chosen in range(len(_TARGETS))
    for position in range(len(_TARGETS))
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("chosen", "position"), _EVERY_POSITION_OF_EACH_CHOICE)
async def test_approval_delivers_to_the_destination_the_card_shows(bus: _FakeBus, chosen: int, position: int) -> None:
    row = _TARGETS[chosen]
    destination = f"{row['channel']}:{row['label']}"
    others = [target for index, target in enumerate(_TARGETS) if index != chosen]
    configured = (*others[:position], row, *others[position:])
    agent = _agent(configured, {"destination": destination, "body": "weekly report"})

    _, shown = _card(await _start(agent))
    assert shown["destination"] == destination
    assert bus.delivered == []

    reply = _tool_reply(await _decide(agent, "approve"))
    assert reply == f"Notification sent successfully to {destination}."
    assert bus.delivered == [(row["channel"], row["recipient_id"], "weekly report")]


@pytest.mark.asyncio
async def test_card_marks_the_send_as_not_to_be_taken_back(bus: _FakeBus) -> None:
    review, _ = _card(await _start(_agent(_TARGETS, {"destination": "slack:ops", "body": "hi"})))
    assert review["sociallyIrreversible"] is True
    assert review["hideAllowAlways"] is True


@pytest.mark.asyncio
async def test_rejecting_delivers_nothing(bus: _FakeBus) -> None:
    agent = _agent(_TARGETS, {"destination": "slack:ops", "body": "hi"})
    _card(await _start(agent))
    await _decide(agent, "reject")
    assert bus.delivered == []


@pytest.mark.asyncio
async def test_yolo_session_still_waits_for_the_person(bus: _FakeBus) -> None:
    set_security_config(SecurityConfig(yolo_mode_enabled=True, privacy_policy=PrivacyPolicy(enabled=False)))
    agent = _agent(_TARGETS, {"destination": "slack:ops", "body": "hi"})
    _card(await _start(agent))
    assert bus.delivered == []


_NOT_A_CHOICE = "Input should be 'telegram:我'"
_NO_DESTINATION = "destination: Field required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("args", "complaint"),
    [
        pytest.param({"destination": "telegram:111", "body": "x"}, _NOT_A_CHOICE, id="recipient-id-instead-of-the-name"),
        pytest.param({"destination": "Telegram:我", "body": "x"}, _NOT_A_CHOICE, id="different-case"),
        pytest.param({"destination": "telegram", "body": "x"}, _NOT_A_CHOICE, id="channel-only"),
        pytest.param({"destination": "我", "body": "x"}, _NOT_A_CHOICE, id="label-only"),
        pytest.param({"destination": "", "body": "x"}, _NOT_A_CHOICE, id="empty"),
        pytest.param({"body": "x"}, _NO_DESTINATION, id="no-destination"),
        pytest.param({"channel": "telegram", "target": "111", "body": "x"}, _NO_DESTINATION, id="former-channel-and-target"),
        pytest.param({"channel": "", "target": "我", "body": "x"}, _NO_DESTINATION, id="former-label-as-target"),
    ],
)
async def test_call_outside_the_configured_destinations_delivers_nothing(
    bus: _FakeBus, args: dict[str, object], complaint: str
) -> None:
    agent = _agent(_ONE_TARGET, args)
    state = await _start(agent)
    if "__interrupt__" in state:
        state = await _decide(agent, "approve")

    assert complaint in _tool_reply(state)
    assert bus.delivered == []
