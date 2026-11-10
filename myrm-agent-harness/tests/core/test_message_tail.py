"""Contract tests of the tail-of-turn injection primitive in ``core/message_tail``.

The primitive is shared by the delta and proactive-pack injectors and by the todo and goal focus notices, so
its targeting rule (the user's own latest message, never a notice the runtime appended behind it) is locked here.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.core.message_origin import runtime_human_message
from myrm_agent_harness.core.message_tail import append_block_to_last_user_message

_BLOCK = "<block>payload</block>"
_IMAGE_PART = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


def test_string_content_gets_the_block_after_a_blank_line() -> None:
    out = append_block_to_last_user_message([SystemMessage(content="sys"), HumanMessage(content="question")], _BLOCK)

    assert out[-1].content == f"question\n\n{_BLOCK}"


def test_empty_string_content_becomes_the_block() -> None:
    assert append_block_to_last_user_message([HumanMessage(content="")], _BLOCK)[-1].content == _BLOCK


def test_only_the_last_user_message_changes_and_the_input_stays_untouched() -> None:
    history = [
        SystemMessage(content="sys"),
        HumanMessage(content="first"),
        AIMessage(content="answer"),
        HumanMessage(content="second"),
        AIMessage(content="tool call pending"),
    ]
    snapshot = [m.content for m in history]

    out = append_block_to_last_user_message(history, _BLOCK)

    assert [m.content for m in history] == snapshot
    assert out[:3] == history[:3]
    assert out[4] is history[4]
    assert out[3].content == f"second\n\n{_BLOCK}"


def test_a_runtime_notice_behind_the_user_message_is_skipped() -> None:
    notice = runtime_human_message("[constraint] no network")
    history = [
        HumanMessage(content="question", id="u1"),
        AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
        ToolMessage(content="out", tool_call_id="c1"),
        notice,
    ]

    out = append_block_to_last_user_message(history, _BLOCK)

    assert out[0].content == f"question\n\n{_BLOCK}"
    assert out[0].id == "u1"
    assert out[-1] is notice


def test_history_with_only_runtime_notices_is_returned_unmodified() -> None:
    history = [SystemMessage(content="sys"), runtime_human_message("notice")]

    out = append_block_to_last_user_message(history, _BLOCK)

    assert out == history
    assert out is not history


def test_metadata_of_the_human_message_survives() -> None:
    original = HumanMessage(content="q", id="m-1", name="ada", additional_kwargs={"origin": "cli"})

    updated = append_block_to_last_user_message([original], _BLOCK)[-1]

    assert (updated.id, updated.name, updated.additional_kwargs) == ("m-1", "ada", {"origin": "cli"})
    assert updated.additional_kwargs is not original.additional_kwargs


def test_multimodal_parts_stay_untouched_and_one_text_part_is_appended() -> None:
    parts = [{"type": "text", "text": "what is in this picture"}, _IMAGE_PART, "bare text part"]

    updated = append_block_to_last_user_message([HumanMessage(content=list(parts))], _BLOCK)[-1]

    assert updated.content == [*parts, {"type": "text", "text": f"\n\n{_BLOCK}"}]


def test_empty_block_or_missing_user_message_returns_an_equal_copy() -> None:
    history = [SystemMessage(content="sys"), HumanMessage(content="q")]
    no_human = [SystemMessage(content="sys"), AIMessage(content="a")]

    assert append_block_to_last_user_message(history, "") == history
    assert append_block_to_last_user_message(history, "") is not history
    assert append_block_to_last_user_message(no_human, _BLOCK) == no_human
    assert append_block_to_last_user_message([], _BLOCK) == []


def test_the_same_block_on_the_same_history_gives_the_same_message() -> None:
    """Two requests of one run build the user's message from the same bytes."""
    history = [HumanMessage(content="q", id="u1"), runtime_human_message("notice")]

    first = append_block_to_last_user_message(history, _BLOCK)
    second = append_block_to_last_user_message(history, _BLOCK)

    assert first[0].content == second[0].content
