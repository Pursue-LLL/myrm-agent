"""Compress never rewrites a tool result the model has not read yet.

A result with no AIMessage after it is the unread tail of the step in progress, or the answer a user message cut
short: the next model call needs it verbatim. Unread results hold keep_recent_calls survivor slots ahead of any
priority ranking; the slots left over go to the results the model has already read, by priority and then recency.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.infra.schemas import ContextConfig
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.compress_processor import CompressProcessor
from myrm_agent_harness.agent.context_management.strategies.compactor.compactor import compress_messages_async
from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

_KEEP = 3
_FOCUS_FILE = "src/auth/login.py"


def _body(tag: str) -> str:
    """A result worth compressing; the tag keeps every body distinct so that none is deduplicated."""
    return f"{tag}: " + "alpha beta gamma delta " * 200


def _calls(*indexes: int) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"id": f"c{i}", "name": "shell", "args": {"cmd": f"step-{i}"}} for i in indexes]
    )


def _result(index: int, content: str, *, name: str = "shell") -> ToolMessage:
    return ToolMessage(content=content, name=name, tool_call_id=f"c{index}")


def _group(index: int, content: str) -> list[BaseMessage]:
    return [_calls(index), _result(index, content)]


def _outranking_history(kind: str) -> list[BaseMessage]:
    """Seven groups the model has read that outrank a plain result: failed ones, or ones that touch the focus file."""
    messages: list[BaseMessage] = [HumanMessage(content="fix the login timeout")]
    for i in range(7):
        if kind == "error":
            messages += _group(i, "[ERROR] " + _body(f"old{i}"))
        else:
            call = {"id": f"c{i}", "name": "read_file", "args": {"path": _FOCUS_FILE}}
            messages += [
                AIMessage(content="", tool_calls=[call]),
                _result(i, _body(f"old{i}"), name="read_file"),
            ]
    return messages


def _results(messages: Sequence[BaseMessage]) -> dict[str, str]:
    return {m.tool_call_id: str(m.content) for m in messages if isinstance(m, ToolMessage)}


def _rewritten(before: Sequence[BaseMessage], after: Sequence[BaseMessage]) -> set[str]:
    """Call ids whose result differs between the two lists."""
    original = _results(before)
    return {call_id for call_id, content in _results(after).items() if content != original[call_id]}


async def _compressed(messages: list[BaseMessage], *, focus: bool = False) -> set[str]:
    """Call ids Compress rewrites (it mutates the messages it is given, so it gets a copy)."""
    result, _ = await compress_messages_async(
        copy.deepcopy(messages),
        dynamic_min_save=0,
        config=ContextConfig(max_context_tokens=128_000, keep_recent_calls=_KEEP),
        focus_files=frozenset({_FOCUS_FILE}) if focus else None,
    )
    return _rewritten(messages, result)


@pytest.mark.parametrize("kind", ["error", "focus"])
async def test_a_result_the_model_has_not_read_is_never_compressed(kind: str) -> None:
    messages = [*_outranking_history(kind), *_group(7, _body("newest"))]

    assert "c7" not in await _compressed(messages, focus=kind == "focus")


async def test_every_result_of_an_unread_parallel_call_stays_intact() -> None:
    messages = [
        *_outranking_history("error"),
        _calls(7, 8, 9),
        *(_result(i, _body(f"new{i}")) for i in (7, 8, 9)),
    ]

    compressed = await _compressed(messages)

    assert not {"c7", "c8", "c9"} & compressed
    assert compressed == {f"c{i}" for i in range(7)}


async def test_a_user_message_before_the_model_reads_the_result_keeps_it_intact() -> None:
    messages = [
        *_outranking_history("error"),
        *_group(7, _body("newest")),
        HumanMessage(content="also check the retry logic"),
    ]

    assert "c7" not in await _compressed(messages)


@pytest.mark.parametrize("kind", ["error", "focus"])
async def test_a_result_the_model_has_read_is_still_compressed(kind: str) -> None:
    messages = [*_outranking_history(kind), *_group(7, _body("newest")), AIMessage(content="The timeout is in login.")]

    assert "c7" in await _compressed(messages, focus=kind == "focus")


async def test_unread_results_hold_survivor_slots_and_the_best_read_result_takes_the_rest() -> None:
    messages = [*_outranking_history("error"), _calls(7, 8), *(_result(i, _body(f"new{i}")) for i in (7, 8))]

    assert await _compressed(messages) == {f"c{i}" for i in range(6)}


async def test_among_read_results_priority_decides_before_recency() -> None:
    messages = [*_outranking_history("error"), *_group(7, _body("newest")), AIMessage(content="noted")]

    assert await _compressed(messages) == {"c0", "c1", "c2", "c3", "c7"}


@pytest.mark.parametrize("cache_is_hot", [True, False], ids=["hot-cache", "cold-cache"])
async def test_the_processor_compresses_read_results_and_leaves_the_unread_tail(cache_is_hot: bool) -> None:
    messages = [*_outranking_history("error"), *_group(7, _body("newest"))]
    window = int(estimate_messages_tokens(messages) / 0.93)
    processor = CompressProcessor(max_context_tokens=window, keep_recent_calls=_KEEP, compress_min_save=500)
    last_activity = time.time() if cache_is_hot else time.time() - 400.0
    context = ProcessorContext(
        messages=copy.deepcopy(messages), user_query="x", chat_id=None, metadata={"last_activity_time": last_activity}
    )

    assert await processor.should_process(context) is True
    rewritten = _rewritten(messages, (await processor.process(context)).messages)

    assert rewritten
    assert "c7" not in rewritten
