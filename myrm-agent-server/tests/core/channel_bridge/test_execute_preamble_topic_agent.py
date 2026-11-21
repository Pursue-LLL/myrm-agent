"""The agent that serves a topic's turn is the one its binding names; a frozen identity or no agent at all means the default agent.

The agent decides the profile the turn runs with and the conversation it is stored in, so the preamble hands both the same
agent id and never looks up a profile for an agent that does not serve the turn.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.channels.types import TopicContext

from .preamble_testkit import PreambleProbe, inbound_message, prepare, stubbed_preamble


@pytest.fixture
def preamble() -> Iterator[PreambleProbe]:
    with stubbed_preamble() as probe:
        yield probe


@pytest.mark.asyncio
async def test_the_agent_a_topic_is_bound_to_serves_its_turn(preamble: PreambleProbe) -> None:
    await prepare(inbound_message(), TopicContext(topic_id="t", agent_id="agent-a"))

    preamble.profiles.resolve.assert_awaited_once_with("agent-a")
    assert preamble.session.await_args.kwargs["resolved_agent_id"] == "agent-a"
    assert preamble.builder.await_args.kwargs["resolved_agent_id"] == "agent-a"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "topic",
    [
        pytest.param(None, id="no-binding"),
        pytest.param(TopicContext(topic_id="t"), id="binding-without-agent"),
        pytest.param(TopicContext(topic_id="t", agent_id=""), id="empty-agent"),
        pytest.param(TopicContext(topic_id="t", agent_id="agent-a", identity_revoked=True), id="frozen-identity"),
    ],
)
async def test_a_turn_no_agent_claims_is_served_by_the_default_agent(preamble: PreambleProbe, topic: TopicContext | None) -> None:
    await prepare(inbound_message(), topic)

    preamble.profiles.resolve.assert_not_awaited()
    assert preamble.session.await_args.kwargs["resolved_agent_id"] is None
    assert preamble.builder.await_args.kwargs["resolved_agent_id"] is None
