# [POS]: tests/unit/toolkits/memory/test_append_block_to_last_human.py
# [INPUT]: myrm_agent_harness.toolkits.memory.ephemeral_delta.tail_injector
# [OUTPUT]: Contract tests of the tail-of-turn injection primitive shared by the delta and knowledge-pack middlewares

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from myrm_agent_harness.toolkits.memory.ephemeral_delta import EphemeralDeltaItem, HumanTailDeltaInjector
from myrm_agent_harness.toolkits.memory.ephemeral_delta.tail_injector import append_block_to_last_human

_BLOCK = "<block>payload</block>"
_IMAGE_PART = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


def test_string_content_gets_the_block_after_a_blank_line() -> None:
    out = append_block_to_last_human([SystemMessage(content="sys"), HumanMessage(content="question")], _BLOCK)

    assert out[-1].content == f"question\n\n{_BLOCK}"


def test_empty_string_content_becomes_the_block() -> None:
    assert append_block_to_last_human([HumanMessage(content="")], _BLOCK)[-1].content == _BLOCK


def test_only_the_last_human_message_changes_and_the_input_stays_untouched() -> None:
    history = [
        SystemMessage(content="sys"),
        HumanMessage(content="first"),
        AIMessage(content="answer"),
        HumanMessage(content="second"),
        AIMessage(content="tool call pending"),
    ]
    snapshot = [m.content for m in history]

    out = append_block_to_last_human(history, _BLOCK)

    assert [m.content for m in history] == snapshot
    assert out[:3] == history[:3]
    assert out[4] is history[4]
    assert out[3].content == f"second\n\n{_BLOCK}"


def test_metadata_of_the_human_message_survives() -> None:
    original = HumanMessage(content="q", id="m-1", name="ada", additional_kwargs={"origin": "cli"})

    updated = append_block_to_last_human([original], _BLOCK)[-1]

    assert (updated.id, updated.name, updated.additional_kwargs) == ("m-1", "ada", {"origin": "cli"})
    assert updated.additional_kwargs is not original.additional_kwargs


def test_multimodal_parts_stay_untouched_and_one_text_part_is_appended() -> None:
    parts = [{"type": "text", "text": "what is in this picture"}, _IMAGE_PART, "bare text part"]

    updated = append_block_to_last_human([HumanMessage(content=list(parts))], _BLOCK)[-1]

    assert updated.content == [*parts, {"type": "text", "text": f"\n\n{_BLOCK}"}]


def test_empty_block_or_missing_human_message_returns_an_equal_copy() -> None:
    history = [SystemMessage(content="sys"), HumanMessage(content="q")]
    no_human = [SystemMessage(content="sys"), AIMessage(content="a")]

    assert append_block_to_last_human(history, "") == history
    assert append_block_to_last_human(history, "") is not history
    assert append_block_to_last_human(no_human, _BLOCK) == no_human
    assert append_block_to_last_human([], _BLOCK) == []


def test_delta_injector_keeps_multimodal_parts_intact() -> None:
    delta = EphemeralDeltaItem(delta_id="d-1", target_key="port", content="use 8082")
    message = HumanMessage(content=[{"type": "text", "text": "look"}, _IMAGE_PART])

    updated = HumanTailDeltaInjector().inject_deltas([message], [delta])[-1]

    assert updated.content[1] == _IMAGE_PART
    assert "use 8082" in str(updated.content[-1])
