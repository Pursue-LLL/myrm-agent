"""ThinkingBlockCleaner and signed reasoning: a block lives exactly as long as the tool loop that produced it.

The provider takes finished turns without their reasoning, but a block it signed is valid only in the prompt it was
written under. Once the user speaks again the old prompt is gone, so the blocks of finished turns are removed for good.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.thinking_cleaner import ThinkingBlockCleaner
from myrm_agent_harness.core.message_origin import runtime_human_message
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY

_CLAUDE = "anthropic/claude-sonnet-4-5"
_BEDROCK_CLAUDE = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


class _Model:
    wire_protocol = None

    def __init__(self, name: str) -> None:
        self.model_name = name


def _blocks(label: str) -> list[dict[str, str]]:
    return [{"type": "thinking", "thinking": f"reasoning {label}", "signature": f"sig-{label}"}]


def _round(label: str) -> list[BaseMessage]:
    call = {"name": "search", "args": {}, "id": label, "type": "tool_call"}
    reasoning = AIMessage(content="", tool_calls=[call], additional_kwargs={THINKING_BLOCKS_KEY: _blocks(label)})
    return [reasoning, ToolMessage(content=f"result {label}", tool_call_id=label)]


async def _clean(messages: list[BaseMessage], model: str = _CLAUDE) -> ProcessorContext:
    context = ProcessorContext(messages=messages, user_query="q", llm=_Model(model))
    return await ThinkingBlockCleaner().process(context)


def _kept(messages: list[BaseMessage]) -> list[bool]:
    return [THINKING_BLOCKS_KEY in m.additional_kwargs for m in messages if isinstance(m, AIMessage)]


@pytest.mark.asyncio
async def test_the_blocks_of_the_tool_loop_in_progress_stay() -> None:
    messages = [HumanMessage(content="go"), *_round("c1"), *_round("c2")]

    await _clean(messages)

    assert _kept(messages) == [True, True]


@pytest.mark.asyncio
async def test_the_blocks_of_a_finished_turn_go_when_the_user_speaks_again() -> None:
    finished = [HumanMessage(content="first"), *_round("c1"), AIMessage(content="done")]
    messages = [*finished, HumanMessage(content="second"), *_round("c2")]

    await _clean(messages)

    assert _kept(messages) == [False, False, True]


@pytest.mark.asyncio
async def test_a_notice_the_runtime_added_does_not_end_the_turn() -> None:
    messages = [HumanMessage(content="go"), *_round("c1"), runtime_human_message("note"), *_round("c2")]

    await _clean(messages)

    assert _kept(messages) == [True, True]


@pytest.mark.asyncio
async def test_the_pruned_text_is_counted_as_saved_tokens() -> None:
    messages = [HumanMessage(content="first"), *_round("c1"), HumanMessage(content="second")]
    messages[1].additional_kwargs[THINKING_BLOCKS_KEY].append({"type": "redacted_thinking", "data": "x" * 40})

    context = await _clean(messages)

    assert context.tokens_saved == (len("reasoning c1") + 40) // 4


@pytest.mark.asyncio
async def test_a_second_pass_finds_nothing_left_to_prune() -> None:
    messages = [HumanMessage(content="first"), *_round("c1"), HumanMessage(content="second")]
    await _clean(messages)

    again = await _clean(messages)

    assert again.tokens_saved == 0
    assert _kept(messages) == [False]


@pytest.mark.asyncio
async def test_a_bedrock_hosted_claude_is_pruned_the_same_way() -> None:
    messages = [HumanMessage(content="first"), *_round("c1"), HumanMessage(content="second"), *_round("c2")]

    await _clean(messages, _BEDROCK_CLAUDE)

    assert _kept(messages) == [False, True]


@pytest.mark.asyncio
async def test_a_model_that_is_not_claude_keeps_none_of_them() -> None:
    messages = [HumanMessage(content="go"), *_round("c1")]

    await _clean(messages, "openai/gpt-4")

    assert _kept(messages) == [False]
