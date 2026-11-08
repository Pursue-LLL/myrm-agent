"""The local token count of a stream the provider reported no usage for, and where it enters the accounting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage

from myrm_agent_harness.toolkits.llms.adapters.stream_aggregator import StreamAggregator, finalize_stream
from myrm_agent_harness.toolkits.llms.adapters.usage_estimate import estimate_stream_usage

ToolCalls = Sequence[Mapping[str, object]]

_WEATHER_CALL = {
    "id": "call_1",
    "function": {"name": "get_weather", "arguments": '{"city": "Paris", "unit": "celsius"}'},
}
_HISTORY: list[BaseMessage] = [
    SystemMessage(content="You are helpful."),
    HumanMessage(content="Hi"),
    AIMessage(content="Hello! How can I help?"),
    HumanMessage(content="Tell me about Paris."),
    AIMessage(content="Paris is the capital of France."),
    HumanMessage(content="And its river?"),
]


class TestEstimateStreamUsage:
    @pytest.mark.parametrize(
        ("messages", "text", "tool_calls", "expected"),
        [
            (
                [HumanMessage(content="What is the capital of France?")],
                "Paris is the capital of France.",
                [],
                (14, 7, 21),
            ),
            (
                [SystemMessage(content="You are a concise geography assistant."), HumanMessage(content="Capital?")],
                "Paris.",
                [],
                (20, 2, 22),
            ),
            (_HISTORY, "Paris is the capital of France.", [], (55, 7, 62)),
            ([HumanMessage(content="请介绍一下巴黎。")], "巴黎是法国的首都，位于塞纳河畔。", [], (12, 15, 27)),
            ([HumanMessage(content="What is the weather in Paris?")], "", [_WEATHER_CALL], (14, 36, 50)),
        ],
        ids=["single-user", "system-and-user", "history", "chinese", "tool-call"],
    )
    def test_prompt_and_answer_are_counted_the_way_a_chat_provider_counts_them(
        self, messages: list[BaseMessage], text: str, tool_calls: ToolCalls, expected: tuple[int, int, int]
    ) -> None:
        usage = estimate_stream_usage(messages, text=text, tool_calls=tool_calls)

        assert (usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"]) == expected

    def test_nothing_sent_and_nothing_written_still_costs_the_reply_priming(self) -> None:
        assert estimate_stream_usage([], text="", tool_calls=[]) == {
            "prompt_tokens": 3,
            "completion_tokens": 0,
            "total_tokens": 3,
        }

    def test_a_tool_call_is_counted_with_its_envelope_not_just_its_name_and_arguments(self) -> None:
        bare = estimate_stream_usage([], text="get_weather" + str(_WEATHER_CALL["function"]), tool_calls=[])
        called = estimate_stream_usage([], text="", tool_calls=[_WEATHER_CALL])

        assert called["completion_tokens"] > bare["completion_tokens"]

    def test_a_half_assembled_tool_call_is_counted_without_failing(self) -> None:
        usage = estimate_stream_usage([], text="", tool_calls=[{}, {"function": None, "id": None}, {"function": {}}])

        assert usage["completion_tokens"] > 0
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def _aggregator(*, usage: object | None, content: Sequence[str], reasoning: Sequence[str] = ()) -> StreamAggregator:
    agg = StreamAggregator(AIMessageChunk, [HumanMessage(content="hi")])
    agg.content = list(content)
    agg.reasoning = list(reasoning)
    agg.last_model = "gpt-4o"
    agg.finish_reason = "stop"
    agg.last_usage = usage
    return agg


def _finalize(agg: StreamAggregator) -> tuple[dict[str, object], MagicMock]:
    record = MagicMock()
    result = finalize_stream(agg, None, "gpt-4o", is_async=False, record_usage_fn=record)
    return result.aggregated_response, record


class TestFinalizeStreamUsage:
    def test_the_usage_a_provider_reported_is_recorded_as_it_came(self) -> None:
        reported = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

        response, record = _finalize(_aggregator(usage=reported, content=["hello"]))

        assert record.call_args.args[0] is reported
        assert response["usage"] == reported

    def test_a_stream_without_usage_is_recorded_from_a_local_count(self) -> None:
        _, record = _finalize(_aggregator(usage=None, content=["hel", "lo"]))

        assert record.call_args.args[0] == {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9}

    def test_the_local_count_never_becomes_the_usage_of_the_answer(self) -> None:
        response, _ = _finalize(_aggregator(usage=None, content=["hello"]))

        assert response["usage"] == {}

    def test_reasoning_a_model_wrote_is_part_of_the_count(self) -> None:
        _, plain = _finalize(_aggregator(usage=None, content=["hello"]))
        _, thinking = _finalize(_aggregator(usage=None, content=["hello"], reasoning=["Let me think about this."]))

        assert thinking.call_args.args[0]["completion_tokens"] > plain.call_args.args[0]["completion_tokens"]

    def test_a_tool_call_the_stream_wrote_is_part_of_the_count(self) -> None:
        agg = _aggregator(usage=None, content=[])
        agg.tool_calls = [{"function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}, "id": "call_1"}]

        _, record = _finalize(agg)

        assert record.call_args.args[0]["completion_tokens"] > 0

    def test_a_stream_the_provider_never_finished_is_still_accounted_and_marked_dropped(self) -> None:
        from myrm_agent_harness.utils.token_economics.usage_ledger import DROPPED_STREAM_FINISH_REASON

        agg = _aggregator(usage=None, content=["partial"])
        agg.finish_reason = ""

        _, record = _finalize(agg)

        assert record.call_args.args[0]["prompt_tokens"] == 8
        assert record.call_args.kwargs["finish_reason"] == DROPPED_STREAM_FINISH_REASON
