"""A channel turn draws its credentials from the track its identity resolves to, in the agent it builds and the credentials it holds.

A group topic bound to a shared identity runs on the shared track, every other turn on the personal one. The agent's
skills are listed for that track and the turn's credentials are assembled for it, so the two cannot disagree.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security import CredentialTrack

from app.ai_agents.agents import GeneralAgentParams
from app.channels.types import IdentityScopeMode, InboundMessage, TopicContext

from .preamble_testkit import build_agent, inbound_message, prepare, stubbed_preamble

_AGENT = "app.core.channel_bridge.agent_executor.execute_preamble.agent"
_TRACKS = [CredentialTrack.PERSONAL, CredentialTrack.SHARED]


@pytest.fixture
def agent_builder() -> Iterator[AsyncMock]:
    """The agent-building step of the preamble, with every other collaborator of the preamble stood in for."""
    with stubbed_preamble() as probe:
        yield probe.builder


@pytest.mark.asyncio
async def test_a_group_topic_bound_to_a_shared_identity_runs_on_the_shared_track(agent_builder: AsyncMock) -> None:
    group_message = InboundMessage(
        channel="feishu", sender_id="u1", content="hi", chat_id="chat9", is_group=True, mentioned=True, metadata={"locale": "en"}
    )
    topic = TopicContext(topic_id="chat9", agent_id="a1", identity_scope=IdentityScopeMode.SHARED, identity_id="yifu")

    await prepare(group_message, topic)

    assert agent_builder.await_args.kwargs["credential_track"] is CredentialTrack.SHARED


@pytest.mark.asyncio
async def test_a_direct_chat_runs_on_the_personal_track(agent_builder: AsyncMock) -> None:
    await prepare(inbound_message(), None)

    assert agent_builder.await_args.kwargs["credential_track"] is CredentialTrack.PERSONAL


@pytest.mark.asyncio
@pytest.mark.parametrize("track", _TRACKS, ids=lambda track: track.value)
async def test_the_agent_and_its_credentials_are_built_for_the_turns_track(track: CredentialTrack) -> None:
    created: list[GeneralAgentParams] = []

    def _create_agent(params: GeneralAgentParams) -> MagicMock:
        created.append(params)
        return MagicMock()

    assembler = AsyncMock(return_value=())
    with (
        patch(
            "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(f"{_AGENT}.AgentFactory.create_general_agent", side_effect=_create_agent),
        patch("app.services.agent.session_credential_assembler.assemble_session_credentials", assembler),
    ):
        outcome = await build_agent(inbound_message(), credential_track=track)

    assert outcome.result is not None
    assert created[0].credential_track is track
    assert assembler.await_args.kwargs["credential_track"] is track
