"""The summary call runs under a prompt of its own, so it never replays the conversation's signed reasoning.

A reasoning block the provider signed is valid only under the system prompt and tool set it was written for. The
summary call sends the conversation under another prompt: a block in it would be refused, and the summary with it.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.strategies.summary.summarizer import (
    _build_summary_invocation_messages,
)
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY

_BLOCKS = [{"type": "thinking", "thinking": "plan", "signature": "sig-1"}]


def _conversation() -> list[BaseMessage]:
    call = {"name": "grep_tool", "args": {"pattern": "a"}, "id": "a", "type": "tool_call"}
    return [
        HumanMessage(content="find a"),
        AIMessage(content="", tool_calls=[call], additional_kwargs={THINKING_BLOCKS_KEY: _BLOCKS}),
        ToolMessage(content="hit a", tool_call_id="a", name="grep_tool"),
        AIMessage(content="found", additional_kwargs={THINKING_BLOCKS_KEY: _BLOCKS}),
    ]


def test_the_summary_call_is_sent_the_conversation_without_its_signed_reasoning() -> None:
    conversation = _conversation()

    sent = _build_summary_invocation_messages("summarize", conversation)

    assert [THINKING_BLOCKS_KEY in message.additional_kwargs for message in sent] == [False] * len(sent)
    assert [message.content for message in sent[:-1]] == [message.content for message in conversation]
    assert isinstance(sent[-1], HumanMessage)
    assert sent[-1].content == "summarize"


def test_the_conversation_itself_keeps_the_reasoning_its_next_request_replays() -> None:
    conversation = _conversation()

    _build_summary_invocation_messages("summarize", conversation)

    assert conversation[1].additional_kwargs[THINKING_BLOCKS_KEY] == _BLOCKS
    assert conversation[3].additional_kwargs[THINKING_BLOCKS_KEY] == _BLOCKS
