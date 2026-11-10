"""Tests for ThinkingBlockCleaner processor.

Covers:
- Anthropic: remove reasoning_content, keep thinking_blocks
- Non-Anthropic: selective reasoning_content cleanup based on tool_calls + position
- chars_dropped telemetry

Edge cases, turn boundary and model switches live in test_thinking_cleaner_edge_cases.py.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.thinking_cleaner import ThinkingBlockCleaner


def _ctx(messages, model_name="openai/gpt-4", wire_protocol=None):
    class FakeLLM:
        def __init__(self, name, wire):
            self.model_name = name
            self.wire_protocol = wire

    return ProcessorContext(messages=messages, user_query="test", llm=FakeLLM(model_name, wire_protocol))


# ── should_process gate ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_should_process_no_thinking():
    cleaner = ThinkingBlockCleaner()
    ctx = _ctx([HumanMessage(content="hi"), AIMessage(content="hello")])
    assert not await cleaner.should_process(ctx)


@pytest.mark.asyncio
async def test_should_process_has_reasoning():
    cleaner = ThinkingBlockCleaner()
    msg = AIMessage(content="answer", additional_kwargs={"reasoning_content": "I think..."})
    ctx = _ctx([msg])
    assert await cleaner.should_process(ctx)


# ── Anthropic path ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clean_reasoning_for_anthropic():
    """Anthropic: reasoning_content removed, thinking_blocks kept."""
    cleaner = ThinkingBlockCleaner()
    msg = AIMessage(
        content="answer",
        additional_kwargs={
            "reasoning_content": "I reasoned about...",
            "thinking_blocks": [{"type": "thinking", "thinking": "deep thought"}],
        },
    )
    ctx = _ctx([msg], model_name="anthropic/claude-3-opus-20240229")
    result = await cleaner.process(ctx)

    kwargs = result.messages[0].additional_kwargs
    assert "reasoning_content" not in kwargs
    assert kwargs["thinking_blocks"] == [{"type": "thinking", "thinking": "deep thought"}]


@pytest.mark.asyncio
async def test_anthropic_chars_dropped():
    """Anthropic: chars_dropped tracks removed reasoning_content length."""
    cleaner = ThinkingBlockCleaner()
    rc_text = "x" * 3000
    msg = AIMessage(content="ok", additional_kwargs={"reasoning_content": rc_text})
    ctx = _ctx([msg], model_name="anthropic/claude-sonnet-4-20250514")
    result = await cleaner.process(ctx)
    assert result.tokens_saved == 3000 // 4


# ── Non-Anthropic: selective cleanup ────────────────────────────────


@pytest.mark.asyncio
async def test_plain_text_before_last_human_cleaned():
    """Plain-text assistant msg BEFORE last human → reasoning_content removed."""
    cleaner = ThinkingBlockCleaner()
    rc_text = "thinking about crawlers..." * 100
    messages = [
        HumanMessage(content="write a crawler"),
        AIMessage(content="ok", additional_kwargs={"reasoning_content": rc_text}),
        HumanMessage(content="use requests"),
    ]
    ctx = _ctx(messages, model_name="deepseek/deepseek-v4-flash")
    result = await cleaner.process(ctx)

    assert "reasoning_content" not in result.messages[1].additional_kwargs
    assert result.tokens_saved == len(rc_text) // 4


@pytest.mark.asyncio
async def test_tool_call_before_last_human_preserved():
    """Tool-call assistant msg BEFORE last human → reasoning_content preserved (API requirement)."""
    cleaner = ThinkingBlockCleaner()
    rc_text = "let me write the file..."
    messages = [
        HumanMessage(content="write code"),
        AIMessage(
            content="",
            additional_kwargs={
                "reasoning_content": rc_text,
                "tool_calls": [{"id": "tc1", "function": {"name": "file_write", "arguments": "{}"}}],
            },
        ),
        HumanMessage(content="next"),
    ]
    ctx = _ctx(messages, model_name="deepseek/deepseek-v4-flash")
    result = await cleaner.process(ctx)

    assert result.messages[1].additional_kwargs["reasoning_content"] == rc_text
    assert result.tokens_saved == 0


@pytest.mark.asyncio
async def test_after_last_human_always_preserved():
    """Assistant msg AFTER last human → reasoning_content always preserved."""
    cleaner = ThinkingBlockCleaner()
    rc_text = "latest thinking"
    messages = [
        HumanMessage(content="question"),
        AIMessage(content="answer", additional_kwargs={"reasoning_content": rc_text}),
    ]
    ctx = _ctx(messages, model_name="deepseek/deepseek-v4-flash")
    result = await cleaner.process(ctx)

    assert result.messages[1].additional_kwargs["reasoning_content"] == rc_text


@pytest.mark.asyncio
async def test_langchain_tool_calls_detected():
    """AIMessage.tool_calls (LangChain native) should prevent cleanup."""
    cleaner = ThinkingBlockCleaner()
    rc_text = "planning tool use"
    msg = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": rc_text},
        tool_calls=[{"name": "bash", "args": {"cmd": "ls"}, "id": "tc1"}],
    )
    messages = [HumanMessage(content="list files"), msg, HumanMessage(content="next")]
    ctx = _ctx(messages, model_name="deepseek/deepseek-v4-flash")
    result = await cleaner.process(ctx)

    assert result.messages[1].additional_kwargs["reasoning_content"] == rc_text


@pytest.mark.asyncio
async def test_thinking_blocks_cleaned_for_non_anthropic():
    """Non-Anthropic: thinking_blocks always removed; reasoning_content on latest turn preserved."""
    cleaner = ThinkingBlockCleaner()
    msg = AIMessage(
        content="answer",
        additional_kwargs={
            "reasoning_content": "latest thinking",
            "thinking_blocks": [{"type": "thinking", "thinking": "block"}],
        },
    )
    messages = [HumanMessage(content="prev"), msg]
    ctx = _ctx(messages, model_name="openai/gpt-4o")
    result = await cleaner.process(ctx)

    kwargs = result.messages[1].additional_kwargs
    assert "thinking_blocks" not in kwargs
    assert kwargs["reasoning_content"] == "latest thinking"


@pytest.mark.asyncio
async def test_multi_turn_selective_cleanup():
    """Multi-turn: only plain-text msgs before last human get cleaned."""
    cleaner = ThinkingBlockCleaner()
    messages = [
        HumanMessage(content="q1"),
        AIMessage(content="a1", additional_kwargs={"reasoning_content": "rc1_plain"}),
        HumanMessage(content="q2"),
        AIMessage(
            content="",
            additional_kwargs={
                "reasoning_content": "rc2_tool",
                "tool_calls": [{"id": "tc", "function": {"name": "bash", "arguments": "{}"}}],
            },
        ),
        HumanMessage(content="q3"),
        AIMessage(content="a3", additional_kwargs={"reasoning_content": "rc3_after"}),
    ]
    ctx = _ctx(messages, model_name="deepseek/deepseek-v4-flash")
    result = await cleaner.process(ctx)

    # rc1_plain: before last human, no tool_calls → removed
    assert "reasoning_content" not in result.messages[1].additional_kwargs
    # rc2_tool: before last human but has tool_calls → preserved
    assert result.messages[3].additional_kwargs["reasoning_content"] == "rc2_tool"
    # rc3_after: after last human → preserved
    assert result.messages[5].additional_kwargs["reasoning_content"] == "rc3_after"
    assert result.tokens_saved == len("rc1_plain") // 4


@pytest.mark.asyncio
async def test_no_human_message_preserves_all():
    """No HumanMessage at all → nothing cleaned (last_human_idx = -1)."""
    cleaner = ThinkingBlockCleaner()
    msg = AIMessage(content="solo", additional_kwargs={"reasoning_content": "keep"})
    ctx = _ctx([msg], model_name="deepseek/deepseek-v4-flash")
    result = await cleaner.process(ctx)

    assert result.messages[0].additional_kwargs["reasoning_content"] == "keep"


@pytest.mark.asyncio
async def test_no_llm_cleans_thinking_blocks():
    """When no LLM info, clean thinking_blocks, apply selective reasoning cleanup."""
    cleaner = ThinkingBlockCleaner()
    rc_text = "x" * 500
    msg = AIMessage(
        content="answer",
        additional_kwargs={
            "reasoning_content": rc_text,
            "thinking_blocks": [{"type": "thinking"}],
        },
    )
    messages = [msg, HumanMessage(content="next")]
    ctx = ProcessorContext(messages=messages, user_query="test", llm=None)
    result = await cleaner.process(ctx)

    kwargs = result.messages[0].additional_kwargs
    assert "thinking_blocks" not in kwargs
    assert "reasoning_content" not in kwargs
    assert result.tokens_saved == 500 // 4
