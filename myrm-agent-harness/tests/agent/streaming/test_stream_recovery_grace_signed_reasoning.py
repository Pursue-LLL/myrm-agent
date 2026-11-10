"""The grace call has no system prompt and no tools, so it never replays the run's signed reasoning.

A reasoning block the provider signed is valid only under the prompt it was written for; sent under the grace prompt
it would be refused, and the run would end on the generic fallback text instead of a summary of what it did.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.streaming.stream_executor import StreamContext, StreamExecutor
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY

_BLOCKS = [{"type": "thinking", "thinking": "plan", "signature": "sig-1"}]


class _Compactor:
    async def put(self, event: object) -> None:
        return None

    async def flush(self) -> None:
        return None


def _executor(llm: MagicMock) -> StreamExecutor:
    ctx = StreamContext(
        agent=MagicMock(),
        agent_input={"messages": [HumanMessage(content="test")]},
        merged_context={"locale": "en"},
        run_config={},
        stats=AgentRunStatistics(),
        message_id="grace_signed",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
        llm=llm,
    )
    executor = StreamExecutor(ctx=ctx, fallback_llm=None, safety_fallback_llm=None, rebuild_agent_fn=MagicMock())
    executor._compactor = _Compactor()
    return executor


@pytest.mark.asyncio
async def test_the_grace_call_is_sent_the_run_without_its_signed_reasoning() -> None:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Here is what was done."))
    call = {"name": "grep_tool", "args": {}, "id": "a", "type": "tool_call"}
    collected = [
        HumanMessage(content="q"),
        AIMessage(content="", tool_calls=[call], additional_kwargs={THINKING_BLOCKS_KEY: _BLOCKS}),
        ToolMessage(content="hit", tool_call_id="a", name="grep_tool"),
    ]

    executor = _executor(llm)
    with patch.object(executor, "_emit_message_pair", new_callable=AsyncMock) as emit:
        await executor._grace_call_summary(collected)

    sent = llm.ainvoke.call_args.args[0]
    assert [THINKING_BLOCKS_KEY in message.additional_kwargs for message in sent] == [False] * len(sent)
    assert collected[1].additional_kwargs[THINKING_BLOCKS_KEY] == _BLOCKS
    assert "Here is what was done." in emit.call_args.args[0]
