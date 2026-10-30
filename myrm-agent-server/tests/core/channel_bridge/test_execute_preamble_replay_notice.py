"""A message replayed after a restart reaches the model with a note that it may already have been partly handled."""

from __future__ import annotations

import pytest
from langgraph.types import Command

from app.channels.reliability.inbound_journal import METADATA_IS_RECOVERY
from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.execute_preamble.replay_notice import attach_replay_notice

from .preamble_testkit import build_live_turn, inbound_message

_QUERY = "Rename the report and mail it to Ana."
_NOTICE = (
    "[System notice: this message reached the server before it restarted, so it may already have been partly handled. "
    "Before repeating a step that changes something outside this chat (sending a message, writing a file, running a "
    "command, calling an external service), check whether it was already done; then carry on with the request.]"
)


def _inbound(*, replayed: bool) -> InboundMessage:
    metadata: dict[str, object] = {METADATA_IS_RECOVERY: True} if replayed else {}
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="chat-1", content=_QUERY, metadata=metadata)


def test_a_replayed_text_query_is_followed_by_the_notice() -> None:
    assert attach_replay_notice(_QUERY, _inbound(replayed=True)) == f"{_QUERY}\n\n{_NOTICE}"


def test_a_replayed_query_with_images_gets_the_notice_in_its_text_part_and_keeps_the_images() -> None:
    image: dict[str, object] = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    query: list[dict[str, object]] = [{"type": "text", "text": _QUERY}, image]

    result = attach_replay_notice(query, _inbound(replayed=True))

    assert result == [{"type": "text", "text": f"{_QUERY}\n\n{_NOTICE}"}, image]
    assert query[0] == {"type": "text", "text": _QUERY}


def test_a_query_without_a_text_part_gets_one_for_the_notice() -> None:
    image: dict[str, object] = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}

    assert attach_replay_notice([image], _inbound(replayed=True)) == [image, {"type": "text", "text": _NOTICE}]


def test_a_message_that_is_not_a_replay_is_unchanged() -> None:
    query: list[dict[str, object]] = [{"type": "text", "text": _QUERY}]

    assert attach_replay_notice(_QUERY, _inbound(replayed=False)) == _QUERY
    assert attach_replay_notice(query, _inbound(replayed=False)) is query


def test_a_flag_that_is_not_set_is_not_a_replay() -> None:
    msg = _inbound(replayed=False)
    msg.metadata[METADATA_IS_RECOVERY] = False

    assert attach_replay_notice(_QUERY, msg) == _QUERY


@pytest.mark.asyncio
async def test_build_agent_tells_the_model_a_replayed_message_may_be_partly_handled_on_the_live_turn_only() -> None:
    msg = inbound_message()
    msg.metadata[METADATA_IS_RECOVERY] = True

    result, params = await build_live_turn(msg)

    assert result.query_input == f"test query\n\n{_NOTICE}"
    assert params.query == "test query"


@pytest.mark.asyncio
async def test_build_agent_adds_no_notice_to_a_message_that_is_not_a_replay() -> None:
    result, _params = await build_live_turn(inbound_message())

    assert result.query_input == "test query"


@pytest.mark.asyncio
async def test_build_agent_resumes_a_replayed_approval_answer_without_a_notice() -> None:
    msg = inbound_message(resume_value={"decisions": [{"type": "approve"}]})
    msg.metadata[METADATA_IS_RECOVERY] = True

    result, _params = await build_live_turn(msg, is_resume=True)

    assert isinstance(result.query_input, Command)
