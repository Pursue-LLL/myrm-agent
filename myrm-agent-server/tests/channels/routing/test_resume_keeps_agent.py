"""A resumed run goes back to the agent session of the turn that asked.

The session key carries the agent, so a resume that runs without its agent's topic context looks for a chat that does
not exist. Runs on the real ``AgentRouter``, ``SessionGate`` and ``ApprovalTimeoutScheduler`` with a scripted agent; the
last test feeds the contexts the router hands out into the real session lookup on a real database.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.channels.routing.pending_approvals import (
    METADATA_RESUME_AGENT_KEY,
    resume_topic_context,
    session_agent_id,
)
from app.channels.routing.router import AgentRouter
from app.channels.types import (
    ApprovalExpiry,
    InboundMessage,
    ProgressUpdate,
    QuickReply,
    SessionPolicy,
    SessionResetMode,
    StreamingText,
    TopicContext,
)
from app.channels.types.topics import METADATA_ROUTE_AGENT_KEY
from app.core.channel_bridge.agent_executor.execute_preamble.session import resolve_channel_session_context
from tests.support.pending_approvals import inbound_message, router_with_agent

_AGENT = "finance"
_OTHER_AGENT = "support"
_BOUND = TopicContext(topic_id="c1", agent_id=_AGENT, matched_by="chat_binding")
_REBOUND = TopicContext(topic_id="c1", agent_id=_OTHER_AGENT, matched_by="chat_binding")
_LONG = 60.0
_SHORT = 0.05


@pytest.fixture(autouse=True)
def _scheduler() -> Iterator[ApprovalTimeoutScheduler]:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.cancel_all()
    yield scheduler
    scheduler.cancel_all()


def _approval_card(expiry_seconds: float = _LONG) -> ProgressUpdate:
    return ProgressUpdate(
        label="send_email needs approval",
        quick_replies=(QuickReply(label="Approve", text="/approve", required=True),),
        expiry=ApprovalExpiry(seconds=expiry_seconds, behavior="deny"),
    )


class _Agent:
    """The first plain turn stops at a tool approval, a resume finishes its run; the topic context of each call is kept."""

    def __init__(self, expiry_seconds: float = _LONG) -> None:
        self._expiry_seconds = expiry_seconds
        self.contexts: list[TopicContext | None] = []
        self.asked = asyncio.Event()
        self.resumed = asyncio.Event()

    async def execute_stream(self, msg: InboundMessage, user_id: str, **kwargs: object) -> AsyncGenerator[object, None]:
        topic_context = kwargs.get("topic_context")
        self.contexts.append(topic_context if isinstance(topic_context, TopicContext) else None)
        if msg.resume_value is not None:
            yield StreamingText(text="mail sent")
            self.resumed.set()
            return
        yield StreamingText(text="checking")
        yield _approval_card(self._expiry_seconds)
        self.asked.set()


async def _until(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), timeout=5)


def _bound_router(agent: _Agent, topic: TopicContext | None = _BOUND) -> AgentRouter:
    router, _bus = router_with_agent(agent)
    router._resolve_topic = AsyncMock(return_value=topic)  # type: ignore[method-assign]
    return router


async def _asked_and_approved(router: AgentRouter, agent: _Agent, asking: InboundMessage | None = None) -> None:
    router._gate.submit(asking or inbound_message("mail the report"))
    await _until(agent.asked)
    await router._handle_approval_command(inbound_message("/approve"), "allow_once")
    await _until(agent.resumed)


@pytest.mark.asyncio
async def test_an_approved_run_of_an_agent_bound_chat_resumes_in_its_agent() -> None:
    agent = _Agent()
    router = _bound_router(agent)

    await _asked_and_approved(router, agent)

    assert agent.contexts == [_BOUND, _BOUND]


@pytest.mark.asyncio
async def test_an_approved_run_of_an_alias_routed_turn_resumes_in_the_routed_agent() -> None:
    """The alias names the agent on the asking message only; the person's ``/approve`` names none."""
    agent = _Agent()
    router = _bound_router(agent, topic=None)
    asking = inbound_message("mail the report")
    asking = dataclasses.replace(asking, metadata={**asking.metadata, METADATA_ROUTE_AGENT_KEY: _AGENT})

    with patch("app.services.agent.agent_service.AgentService.get_agent_by_id", AsyncMock(return_value=None)):
        await _asked_and_approved(router, agent, asking)

    assert [context.agent_id if context else None for context in agent.contexts] == [_AGENT, _AGENT]
    assert all(context is not None and context.matched_by == "alias" for context in agent.contexts)


@pytest.mark.asyncio
async def test_an_unanswered_approval_of_an_agent_bound_chat_resumes_in_its_agent() -> None:
    agent = _Agent(expiry_seconds=_SHORT)
    router = _bound_router(agent)

    router._gate.submit(inbound_message("mail the report"))
    await _until(agent.resumed)

    assert agent.contexts == [_BOUND, _BOUND]


@pytest.mark.asyncio
async def test_a_delegated_run_asked_without_its_chats_agent_resumes_without_it() -> None:
    """A delegated run executes in the chat's agent-less session, whatever agent the chat is bound to."""
    agent = _Agent()
    router = _bound_router(agent)
    await router._hand_over_delegated_approval(inbound_message("/delegate mail the report"), _approval_card())

    await router._handle_approval_command(inbound_message("/approve"), "allow_once")
    await _until(agent.resumed)

    assert agent.contexts == [None]


@pytest.mark.asyncio
async def test_a_chat_bound_to_another_agent_since_the_ask_does_not_hand_the_run_that_agents_context() -> None:
    agent = _Agent()
    router = _bound_router(agent)
    router._gate.submit(inbound_message("mail the report"))
    await _until(agent.asked)
    router._resolve_topic = AsyncMock(return_value=_REBOUND)  # type: ignore[method-assign]

    await router._handle_approval_command(inbound_message("/approve"), "allow_once")
    await _until(agent.resumed)

    assert agent.contexts == [_BOUND, None]


def _resume_naming(agent_id: str | None) -> InboundMessage:
    metadata: dict[str, object] = {} if agent_id is None else {METADATA_RESUME_AGENT_KEY: agent_id}
    return dataclasses.replace(inbound_message("/approve"), metadata=metadata)


@pytest.mark.parametrize(
    ("topic", "named", "kept"),
    [
        (_BOUND, _AGENT, True),
        (_BOUND, "", False),
        (_BOUND, _OTHER_AGENT, False),
        (_BOUND, None, False),
        (None, _AGENT, False),
        (dataclasses.replace(_BOUND, identity_revoked=True), _AGENT, False),
        (TopicContext(topic_id="c1"), "", False),
    ],
)
def test_a_resume_keeps_the_topic_context_only_when_its_agent_is_the_one_that_asked(
    topic: TopicContext | None, named: str | None, kept: bool
) -> None:
    assert resume_topic_context(topic, _resume_naming(named)) is (topic if kept else None)


@pytest.mark.asyncio
async def test_the_resume_finds_the_chat_the_asking_turn_created(db_session: object) -> None:
    agent = _Agent()
    router = _bound_router(agent)
    await _asked_and_approved(router, agent)
    msg = InboundMessage(channel="telegram", sender_id="u1", content="hi", chat_id="c1")
    session = "app.core.channel_bridge.agent_executor.execute_preamble.session"

    @asynccontextmanager
    async def database() -> AsyncGenerator[object, None]:
        yield db_session

    async def chat_of(topic: TopicContext | None, *, is_resume: bool) -> str:
        context = await resolve_channel_session_context(
            MagicMock(),
            msg,
            query="hi",
            is_resume=is_resume,
            topic_context=None,
            resolved_agent_id=session_agent_id(topic),
            resolved_profile=None,
            personal_settings_dict=None,
        )
        return context.chat_id

    with (
        patch("app.database.connection.get_session", database),
        patch(f"{session}._detect_cold_start", AsyncMock(return_value=False)),
        patch(f"{session}.maybe_backfill_channel_history", AsyncMock()),
        patch(f"{session}.extract_session_policy_safe", return_value=SessionPolicy(mode=SessionResetMode.PERSISTENT)),
    ):
        asked = await chat_of(agent.contexts[0], is_resume=False)
        resumed = await chat_of(agent.contexts[1], is_resume=True)

    assert asked and resumed == asked
