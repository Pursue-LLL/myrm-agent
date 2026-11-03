"""Anthropic Messages answers and event streams, decoded into the chat.completion shape the adapter consumes.

The payloads follow Anthropic's documented response format; no network is involved.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_response,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.http import StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

from .decoding_helpers import feed_events, first_delta, first_finish_reason


class TestAnthropicParse:
    route = resolve_route("anthropic/claude-sonnet-4-5", api_key="k")

    def test_text_answer_with_cache_accounting_folded_into_the_prompt_total(self) -> None:
        answer = anthropic_response.parse(
            self.route,
            {
                "id": "msg_1",
                "model": "claude-sonnet-4-5-20250929",
                "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": " world"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 10,
                    "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 20,
                    "output_tokens": 7,
                },
            },
        )
        choice = answer["choices"][0]  # type: ignore[index]
        assert choice["message"] == {"role": "assistant", "content": "Hello world"}
        assert choice["finish_reason"] == "stop"
        assert answer["model"] == "claude-sonnet-4-5-20250929"
        assert answer["usage"] == {
            "prompt_tokens": 35,
            "completion_tokens": 7,
            "total_tokens": 42,
            "prompt_tokens_details": {"cached_tokens": 20},
            "cache_creation_input_tokens": 5,
            "cache_read_input_tokens": 20,
        }

    def test_thinking_and_tool_use_blocks(self) -> None:
        thinking = {"type": "thinking", "thinking": "Let me check.", "signature": "sig-1"}
        redacted = {"type": "redacted_thinking", "data": "opaque"}
        answer = anthropic_response.parse(
            self.route,
            {
                "content": [
                    thinking,
                    redacted,
                    {"type": "tool_use", "id": "toolu_1", "name": "search", "input": {"q": "météo", "n": 2}},
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
        choice = answer["choices"][0]  # type: ignore[index]
        message = choice["message"]
        assert message["content"] is None
        assert message["reasoning_content"] == "Let me check."
        assert message["thinking_blocks"] == [thinking, redacted]
        assert message["tool_calls"] == [
            {
                "id": "toolu_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "météo", "n": 2}'},
            }
        ]
        assert choice["finish_reason"] == "tool_calls"

    @pytest.mark.parametrize(
        ("stop_reason", "finish"),
        [
            ("end_turn", "stop"),
            ("stop_sequence", "stop"),
            ("max_tokens", "length"),
            # The response filled the context window: it is cut off, whatever the input size was.
            ("model_context_window_exceeded", "length"),
            ("tool_use", "tool_calls"),
            ("refusal", "content_filter"),
            ("something_new", "stop"),
            (None, None),
        ],
    )
    def test_stop_reason_mapping(self, stop_reason: str | None, finish: str | None) -> None:
        answer = anthropic_response.parse(self.route, {"content": [], "stop_reason": stop_reason})
        assert answer["choices"][0]["finish_reason"] == finish  # type: ignore[index]

    def test_a_tool_call_without_input_has_empty_object_arguments(self) -> None:
        answer = anthropic_response.parse(
            self.route, {"content": [{"type": "tool_use", "id": "t", "name": "ping"}], "stop_reason": "tool_use"}
        )
        calls = answer["choices"][0]["message"]["tool_calls"]  # type: ignore[index]
        assert calls[0]["function"]["arguments"] == "{}"

    def test_a_server_tool_runs_provider_side_and_leaves_only_its_answer_text(self) -> None:
        answer = anthropic_response.parse(
            self.route,
            {
                "content": [
                    {"type": "text", "text": "Let me look. "},
                    {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "météo"}},
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_1",
                        "content": [{"type": "web_search_result", "url": "https://example.com", "title": "Météo"}],
                    },
                    {
                        "type": "text",
                        "text": "Sunny.",
                        "citations": [{"type": "web_search_result_location", "url": "https://example.com"}],
                    },
                ],
                "stop_reason": "end_turn",
            },
        )
        choice = answer["choices"][0]  # type: ignore[index]
        assert choice["message"] == {"role": "assistant", "content": "Let me look. Sunny."}
        assert choice["finish_reason"] == "stop"

    def test_a_content_entry_that_is_not_an_object_is_ignored(self) -> None:
        answer = anthropic_response.parse(
            self.route, {"content": ["stray text", {"type": "text", "text": "kept"}], "stop_reason": "end_turn"}
        )
        assert answer["choices"][0]["message"] == {"role": "assistant", "content": "kept"}  # type: ignore[index]


class TestAnthropicStream:
    route = resolve_route("anthropic/claude-sonnet-4-5", api_key="k")

    def _decoder(self) -> StreamDecoder:
        return anthropic_response.decoder(self.route)

    def test_text_stream_ends_with_one_finish_chunk_carrying_merged_usage(self) -> None:
        chunks = feed_events(
            self._decoder(),
            [
                (
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {
                            "id": "msg_1",
                            "model": "claude-sonnet-4-5",
                            "usage": {"input_tokens": 12, "cache_read_input_tokens": 8, "output_tokens": 1},
                        },
                    },
                ),
                ("ping", {"type": "ping"}),
                (
                    "content_block_start",
                    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                ),
                (
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hi"}},
                ),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                (
                    "message_delta",
                    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}},
                ),
                ("message_stop", {"type": "message_stop"}),
            ],
        )
        assert [first_delta(c) for c in chunks] == [{"role": "assistant", "content": ""}, {"content": "Hi"}, {}]
        assert [first_finish_reason(c) for c in chunks] == [None, None, "stop"]
        assert chunks[-1]["usage"] == {
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "prompt_tokens_details": {"cached_tokens": 8},
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 8,
        }
        assert all(c["id"] == "msg_1" for c in chunks)

    @pytest.mark.parametrize(
        ("stop_reason", "finish"),
        [("max_tokens", "length"), ("model_context_window_exceeded", "length"), ("something_new", "stop")],
    )
    def test_the_stop_reason_of_a_streamed_answer_maps_like_the_one_of_a_whole_answer(
        self, stop_reason: str, finish: str
    ) -> None:
        chunks = feed_events(
            self._decoder(),
            [
                ("message_start", {"type": "message_start", "message": {"id": "m", "usage": {"input_tokens": 1}}}),
                (
                    "message_delta",
                    {"type": "message_delta", "delta": {"stop_reason": stop_reason}, "usage": {"output_tokens": 1}},
                ),
                ("message_stop", {"type": "message_stop"}),
            ],
        )
        assert first_finish_reason(chunks[-1]) == finish

    def test_parallel_tool_calls_get_running_zero_based_indexes_and_stream_their_arguments(self) -> None:
        chunks = feed_events(
            self._decoder(),
            [
                ("message_start", {"type": "message_start", "message": {"id": "m", "usage": {"input_tokens": 1}}}),
                (
                    "content_block_start",
                    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                ),
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 1,
                        "content_block": {"type": "tool_use", "id": "toolu_a", "name": "alpha", "input": {}},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 1,
                        "delta": {"type": "input_json_delta", "partial_json": '{"x":'},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 1,
                        "delta": {"type": "input_json_delta", "partial_json": "1}"},
                    },
                ),
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 2,
                        "content_block": {"type": "tool_use", "id": "toolu_b", "name": "beta", "input": {}},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 2,
                        "delta": {"type": "input_json_delta", "partial_json": "{}"},
                    },
                ),
                (
                    "message_delta",
                    {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 9}},
                ),
                ("message_stop", {"type": "message_stop"}),
            ],
        )
        calls = [call for c in chunks for call in first_delta(c).get("tool_calls", [])]  # type: ignore[union-attr]
        assert [(c["index"], c.get("id"), c["function"].get("name"), c["function"]["arguments"]) for c in calls] == [
            (0, "toolu_a", "alpha", ""),
            (0, None, None, '{"x":'),
            (0, None, None, "1}"),
            (1, "toolu_b", "beta", ""),
            (1, None, None, "{}"),
        ]
        assert first_finish_reason(chunks[-1]) == "tool_calls"

    def test_thinking_deltas_are_reasoning_content(self) -> None:
        chunks = feed_events(
            self._decoder(),
            [
                (
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hm"}},
                ),
            ],
        )
        assert first_delta(chunks[0]) == {"reasoning_content": "hm"}

    def test_a_server_tool_streams_no_call_and_leaves_the_callers_tool_numbering_alone(self) -> None:
        chunks = feed_events(
            self._decoder(),
            [
                ("message_start", {"type": "message_start", "message": {"id": "m", "usage": {"input_tokens": 1}}}),
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search"},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "input_json_delta", "partial_json": '{"query": "météo"}'},
                    },
                ),
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 1,
                        "content_block": {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": []},
                    },
                ),
                (
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 2, "delta": {"type": "text_delta", "text": "Sunny."}},
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 2,
                        "delta": {"type": "citations_delta", "citation": {"type": "web_search_result_location"}},
                    },
                ),
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 3,
                        "content_block": {"type": "tool_use", "id": "toolu_a", "name": "alpha", "input": {}},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 3,
                        "delta": {"type": "input_json_delta", "partial_json": "{}"},
                    },
                ),
                (
                    "message_delta",
                    {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 9}},
                ),
                ("message_stop", {"type": "message_stop"}),
            ],
        )
        deltas = [first_delta(c) for c in chunks]
        assert [d["content"] for d in deltas if d.get("content")] == ["Sunny."]
        calls = [call for d in deltas for call in d.get("tool_calls", [])]  # type: ignore[union-attr]
        assert [(c["index"], c.get("id"), c["function"].get("name"), c["function"]["arguments"]) for c in calls] == [
            (0, "toolu_a", "alpha", ""),
            (0, None, None, "{}"),
        ]
        assert first_finish_reason(chunks[-1]) == "tool_calls"

    def test_a_stream_that_never_reports_a_stop_reason_has_no_finish_chunk(self) -> None:
        chunks = feed_events(
            self._decoder(),
            [
                ("message_start", {"type": "message_start", "message": {"id": "m"}}),
                (
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "cut"}},
                ),
            ],
        )
        assert all(first_finish_reason(c) is None for c in chunks)

    def test_an_error_event_raises_with_the_payload(self) -> None:
        payload = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
        with pytest.raises(LLMAnswerError) as caught:
            feed_events(self._decoder(), [("error", payload)])
        assert caught.value.body == payload

    @pytest.mark.parametrize("data", ["not json", "[1, 2]", '{"type": "mystery"}'])
    def test_undecodable_or_unknown_events_are_skipped(self, data: str) -> None:
        assert feed_events(self._decoder(), [(None, data)]) == []

    def test_a_delta_that_is_not_an_object_is_skipped(self) -> None:
        stray = {"type": "content_block_delta", "index": 0, "delta": "stray"}
        assert feed_events(self._decoder(), [("content_block_delta", stray)]) == []
