"""A turn in the owner's direct chat notes where the chat is being talked in; groups, guests and resumed runs do not.

A wake turn runs with the owner's whole memory, so its reply must not go into a conversation that memory is walled off from.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.types import InboundMessage, OutboundMessage, SessionPolicy
from app.core.channel_bridge.agent_executor.execute_preamble.preamble import prepare_channel_execution
from app.core.channel_bridge.agent_executor.execute_preamble.session import ChannelSessionContext
from app.core.channel_bridge.agent_executor.execute_preamble.types import ChannelAgentBuildOutcome
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.channel_bridge.wake_return import WakeOrigins
from app.core.types.business import ModelConfig

_PREAMBLE = "app.core.channel_bridge.agent_executor.execute_preamble.preamble"
_MSG = InboundMessage(channel="telegram", sender_id="u1", content="research it", chat_id="room-1", metadata={"locale": "en"})


@pytest.fixture
def origins() -> Iterator[WakeOrigins]:
    """The memory the turn writes to, with every other collaborator of the preamble stood in for."""
    memory = WakeOrigins()
    configs = UserConfigs(
        model_cfg=ModelConfig(model="test-model", api_key="test-key"),
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict=None,
        personal_settings_dict={},
        mcp_dict=None,
        providers_dict=None,
    )
    early_reply = OutboundMessage(channel="telegram", recipient_id="room-1", content="stop here", user_id="")
    with (
        patch(f"{_PREAMBLE}.get_wake_origins", return_value=memory),
        patch("app.services.budget.enforcer.should_block_execution", AsyncMock(return_value=False)),
        patch("app.services.budget.channel_budget.should_block_channel", return_value=False),
        patch(f"{_PREAMBLE}.load_user_configs", AsyncMock(return_value=configs)),
        patch(
            f"{_PREAMBLE}.build_channel_execution_agent",
            AsyncMock(return_value=ChannelAgentBuildOutcome(early_reply=early_reply)),
        ),
    ):
        yield memory


async def _prepare(chat_id: str, *, is_resume: bool = False, msg: InboundMessage = _MSG, untrusted_sender: bool = False) -> None:
    context = ChannelSessionContext(
        session_key="telegram:room-1",
        chat_id=chat_id,
        chat_history=[],
        session_was_auto_reset=False,
        session_policy=SessionPolicy(),
        query="research it",
        pre_events=(),
    )
    with patch(f"{_PREAMBLE}.resolve_channel_session_context", AsyncMock(return_value=context)):
        await prepare_channel_execution(
            AsyncMock(), msg, is_resume=is_resume, topic_context=None, untrusted_sender=untrusted_sender
        )


@pytest.mark.asyncio
async def test_a_turn_notes_its_message_as_the_origin_of_its_chat(origins: WakeOrigins) -> None:
    await _prepare("chat-db-1")

    origin = origins.get("chat-db-1")
    assert origin is not None and (origin.channel, origin.chat_id) == ("telegram", "room-1")


@pytest.mark.asyncio
async def test_a_turn_that_only_resumes_a_run_leaves_the_origin_as_it_was(origins: WakeOrigins) -> None:
    await _prepare("chat-db-1", is_resume=True)

    assert origins.get("chat-db-1") is None


@pytest.mark.asyncio
async def test_a_turn_whose_chat_could_not_be_opened_notes_nothing(origins: WakeOrigins) -> None:
    await _prepare("")

    assert origins.get("") is None


@pytest.mark.asyncio
async def test_a_group_chat_notes_nothing(origins: WakeOrigins) -> None:
    group_message = InboundMessage(
        channel="telegram", sender_id="u1", content="research it", chat_id="group-1", is_group=True, metadata={"locale": "en"}
    )

    await _prepare("chat-db-1", msg=group_message)

    assert origins.get("chat-db-1") is None


@pytest.mark.asyncio
async def test_a_guests_chat_notes_nothing(origins: WakeOrigins) -> None:
    await _prepare("chat-db-1", untrusted_sender=True)

    assert origins.get("chat-db-1") is None
