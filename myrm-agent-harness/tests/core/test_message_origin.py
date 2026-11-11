"""Contract tests of the message-provenance primitives in ``core/message_origin``.

Every layer that treats the user's message as the start of a turn (the anchors the context pipeline keeps, the blocks the
tail injectors place, the turn counter) relies on these functions agreeing on who wrote a message.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.core.message_origin import (
    count_user_authored_messages,
    is_runtime_system_block,
    is_user_authored_human_message,
    last_user_authored_index,
    runtime_human_message,
    runtime_system_message,
)


def test_a_plain_human_message_is_the_users() -> None:
    assert is_user_authored_human_message(HumanMessage(content="hi"))


def test_runtime_written_human_messages_are_not_the_users() -> None:
    assert not is_user_authored_human_message(runtime_human_message("notice"))
    assert not is_user_authored_human_message(
        HumanMessage(content="x", additional_kwargs={"is_system_synthetic": True})
    )
    assert not is_user_authored_human_message(HumanMessage(content="x", additional_kwargs={"source": "runtime"}))
    assert not is_user_authored_human_message(HumanMessage(content="x", additional_kwargs={"source": "system"}))


def test_a_message_whose_kwargs_are_not_a_mapping_is_still_the_users() -> None:
    # A message rebuilt without validation can lose its kwargs; with no marker to read it is the user's.
    assert is_user_authored_human_message(HumanMessage.model_construct(content="hi", additional_kwargs=None))


def test_other_message_types_are_not_the_users() -> None:
    assert not is_user_authored_human_message(AIMessage(content="a"))
    assert not is_user_authored_human_message(SystemMessage(content="s"))
    assert not is_user_authored_human_message(ToolMessage(content="t", tool_call_id="c"))


def test_the_runtime_message_carries_its_text_and_the_marker() -> None:
    message = runtime_human_message("[constraint] no network")

    assert message.content == "[constraint] no network"
    assert message.additional_kwargs == {"is_system_synthetic": True}


def test_the_turn_starts_at_the_users_message_even_with_runtime_notices_behind_it() -> None:
    history = [
        HumanMessage(content="first"),
        AIMessage(content="answer"),
        HumanMessage(content="second"),
        AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
        ToolMessage(content="out", tool_call_id="c1"),
        runtime_human_message("notice"),
    ]

    assert last_user_authored_index(history) == 2
    assert count_user_authored_messages(history) == 2


def test_no_user_message_means_no_turn() -> None:
    history = [SystemMessage(content="s"), runtime_human_message("notice"), AIMessage(content="a")]

    assert last_user_authored_index(history) == -1
    assert count_user_authored_messages(history) == 0
    assert last_user_authored_index([]) == -1


def test_the_runtime_system_block_carries_its_text_and_the_marker() -> None:
    block = runtime_system_message("<session-access>")

    assert isinstance(block, SystemMessage)
    assert block.content == "<session-access>"
    assert block.additional_kwargs == {"is_system_synthetic": True}
    assert is_runtime_system_block(block)


def test_only_a_system_message_the_runtime_marked_is_a_runtime_system_block() -> None:
    assert not is_runtime_system_block(SystemMessage(content="s"))
    assert not is_runtime_system_block(SystemMessage(content="s", additional_kwargs={"memory_context": True}))
    assert not is_runtime_system_block(SystemMessage(content="s", additional_kwargs={"is_system_synthetic": "yes"}))
    assert not is_runtime_system_block(runtime_human_message("notice"))
    assert not is_runtime_system_block(AIMessage(content="a", additional_kwargs={"is_system_synthetic": True}))


def test_a_system_message_rebuilt_without_its_kwargs_is_no_runtime_block() -> None:
    assert not is_runtime_system_block(SystemMessage.model_construct(content="s", additional_kwargs=None))
