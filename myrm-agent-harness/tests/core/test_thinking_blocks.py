"""Contract tests of the signed reasoning blocks in ``core/thinking_blocks``.

The provider accepts a block back only when it is byte-for-byte what it sent, in order, so every layer that captures,
prunes, estimates or replays blocks relies on these helpers agreeing on what a replayable block is.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.core.thinking_blocks import (
    THINKING_BLOCKS_KEY,
    ThinkingBlockAssembler,
    coerce_thinking_blocks,
    thinking_blocks_text,
    without_thinking_blocks,
)


def test_signed_and_redacted_blocks_are_replayable_and_copied() -> None:
    raw = [
        {"type": "thinking", "thinking": "plan", "signature": "sig-1", "extra": "dropped"},
        {"type": "redacted_thinking", "data": "opaque"},
    ]

    blocks = coerce_thinking_blocks(raw)

    assert blocks == [
        {"type": "thinking", "thinking": "plan", "signature": "sig-1"},
        {"type": "redacted_thinking", "data": "opaque"},
    ]
    assert blocks[0] is not raw[0]


def test_a_block_the_provider_would_refuse_is_dropped() -> None:
    raw = [
        {"type": "thinking", "thinking": "unsigned"},
        {"type": "thinking", "thinking": "empty signature", "signature": ""},
        {"type": "redacted_thinking", "data": ""},
        {"type": "text", "text": "not a reasoning block"},
        "not a mapping",
        {"type": "thinking", "thinking": "kept", "signature": "sig"},
    ]

    assert coerce_thinking_blocks(raw) == [{"type": "thinking", "thinking": "kept", "signature": "sig"}]


def test_an_empty_text_with_a_signature_is_still_a_block() -> None:
    assert coerce_thinking_blocks([{"type": "thinking", "thinking": "", "signature": "sig"}]) == [
        {"type": "thinking", "thinking": "", "signature": "sig"}
    ]
    assert coerce_thinking_blocks([{"type": "thinking", "signature": "sig"}]) == [
        {"type": "thinking", "thinking": "", "signature": "sig"}
    ]


def test_anything_but_a_list_has_no_blocks() -> None:
    assert coerce_thinking_blocks(None) == []
    assert coerce_thinking_blocks("thinking") == []
    assert coerce_thinking_blocks({"type": "thinking", "thinking": "x", "signature": "s"}) == []


def test_the_assembler_joins_the_pieces_of_a_block_under_its_index() -> None:
    assembler = ThinkingBlockAssembler()
    assembler.add_text(0, "first ")
    assembler.add_text(0, "second")
    assembler.add_signature(0, "sig-")
    assembler.add_signature(0, "tail")

    assert assembler.close(0) == {"type": "thinking", "thinking": "first second", "signature": "sig-tail"}
    assert assembler.close(0) is None


def test_the_assembler_keeps_interleaved_blocks_apart() -> None:
    assembler = ThinkingBlockAssembler()
    assembler.set_redacted(2, "opaque")
    assembler.add_text(0, "a")
    assembler.add_signature(0, "s0")

    assert assembler.close(2) == {"type": "redacted_thinking", "data": "opaque"}
    assert assembler.close(0) == {"type": "thinking", "thinking": "a", "signature": "s0"}


def test_a_block_that_ends_unsigned_is_not_emitted() -> None:
    assembler = ThinkingBlockAssembler()
    assembler.add_text(1, "interrupted")

    assert assembler.close(1) is None


def test_an_index_that_held_no_reasoning_yields_nothing() -> None:
    assembler = ThinkingBlockAssembler()

    assert assembler.close(5) is None


def test_a_signature_alone_makes_a_block_with_an_empty_text() -> None:
    assembler = ThinkingBlockAssembler()
    assembler.add_signature(0, "sig")

    assert assembler.close(0) == {"type": "thinking", "thinking": "", "signature": "sig"}


def test_the_reasoning_text_counts_text_and_redacted_data_but_not_the_signature() -> None:
    message = AIMessage(
        content="answer",
        additional_kwargs={
            THINKING_BLOCKS_KEY: [
                {"type": "thinking", "thinking": "plan ", "signature": "x" * 400},
                {"type": "redacted_thinking", "data": "opaque"},
            ]
        },
    )

    assert thinking_blocks_text(message) == "plan opaque"
    assert thinking_blocks_text(AIMessage(content="answer")) == ""
    assert thinking_blocks_text(HumanMessage(content="hi")) == ""


def test_stripping_leaves_the_original_messages_untouched() -> None:
    blocks = [{"type": "thinking", "thinking": "plan", "signature": "sig"}]
    carrying = AIMessage(content="a", additional_kwargs={THINKING_BLOCKS_KEY: blocks, "reasoning_content": "kept"})
    bare = AIMessage(content="b")
    human = HumanMessage(content="hi")

    stripped = without_thinking_blocks([human, carrying, bare])

    assert [m.content for m in stripped] == ["hi", "a", "b"]
    assert THINKING_BLOCKS_KEY not in stripped[1].additional_kwargs
    assert stripped[1].additional_kwargs == {"reasoning_content": "kept"}
    assert carrying.additional_kwargs[THINKING_BLOCKS_KEY] == blocks
    assert stripped[0] is human
    assert stripped[2] is bare
