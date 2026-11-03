"""Answers and event streams of every wire, decoded into the chat.completion shape the adapter consumes.

The payloads follow each vendor's documented response format; no network is involved.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_response,
    gemini_generate,
    ollama_chat,
    openai_chat,
    openai_responses,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMStreamError
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Payload = dict[str, object]


def _feed(decoder: StreamDecoder, events: list[tuple[str | None, Payload | str]]) -> list[Chunk]:
    """Feed events the way the framing layer does, stopping when the decoder says the stream is over."""
    chunks: list[Chunk] = []
    for event, data in events:
        chunks.extend(decoder.feed(event, data if isinstance(data, str) else json.dumps(data)))
        if decoder.done:
            break
    chunks.extend(decoder.finish())
    return chunks


def _delta(chunk: Chunk) -> dict[str, object]:
    choices = chunk["choices"]
    assert isinstance(choices, list)
    delta = choices[0]["delta"]
    assert isinstance(delta, dict)
    return delta


def _finish(chunk: Chunk) -> object:
    choices = chunk["choices"]
    assert isinstance(choices, list)
    return choices[0]["finish_reason"]


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


class TestAnthropicStream:
    route = resolve_route("anthropic/claude-sonnet-4-5", api_key="k")

    def _decoder(self) -> StreamDecoder:
        return anthropic_response.decoder(self.route)

    def test_text_stream_ends_with_one_finish_chunk_carrying_merged_usage(self) -> None:
        chunks = _feed(
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
        assert [_delta(c) for c in chunks] == [{"role": "assistant", "content": ""}, {"content": "Hi"}, {}]
        assert [_finish(c) for c in chunks] == [None, None, "stop"]
        assert chunks[-1]["usage"] == {
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "prompt_tokens_details": {"cached_tokens": 8},
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 8,
        }
        assert all(c["id"] == "msg_1" for c in chunks)

    def test_parallel_tool_calls_get_running_zero_based_indexes_and_stream_their_arguments(self) -> None:
        chunks = _feed(
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
        calls = [call for c in chunks for call in _delta(c).get("tool_calls", [])]  # type: ignore[union-attr]
        assert [(c["index"], c.get("id"), c["function"].get("name"), c["function"]["arguments"]) for c in calls] == [
            (0, "toolu_a", "alpha", ""),
            (0, None, None, '{"x":'),
            (0, None, None, "1}"),
            (1, "toolu_b", "beta", ""),
            (1, None, None, "{}"),
        ]
        assert _finish(chunks[-1]) == "tool_calls"

    def test_thinking_deltas_are_reasoning_content(self) -> None:
        chunks = _feed(
            self._decoder(),
            [
                (
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hm"}},
                ),
            ],
        )
        assert _delta(chunks[0]) == {"reasoning_content": "hm"}

    def test_a_server_tool_streams_no_call_and_leaves_the_callers_tool_numbering_alone(self) -> None:
        chunks = _feed(
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
        deltas = [_delta(c) for c in chunks]
        assert [d["content"] for d in deltas if d.get("content")] == ["Sunny."]
        calls = [call for d in deltas for call in d.get("tool_calls", [])]  # type: ignore[union-attr]
        assert [(c["index"], c.get("id"), c["function"].get("name"), c["function"]["arguments"]) for c in calls] == [
            (0, "toolu_a", "alpha", ""),
            (0, None, None, "{}"),
        ]
        assert _finish(chunks[-1]) == "tool_calls"

    def test_a_stream_that_never_reports_a_stop_reason_has_no_finish_chunk(self) -> None:
        chunks = _feed(
            self._decoder(),
            [
                ("message_start", {"type": "message_start", "message": {"id": "m"}}),
                (
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "cut"}},
                ),
            ],
        )
        assert all(_finish(c) is None for c in chunks)

    def test_an_error_event_raises_with_the_payload(self) -> None:
        payload = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
        with pytest.raises(LLMStreamError) as caught:
            _feed(self._decoder(), [("error", payload)])
        assert caught.value.body == payload

    @pytest.mark.parametrize("data", ["not json", "[1, 2]", '{"type": "mystery"}'])
    def test_undecodable_or_unknown_events_are_skipped(self, data: str) -> None:
        assert _feed(self._decoder(), [(None, data)]) == []


class TestGeminiParse:
    route = resolve_route("gemini/gemini-2.5-pro", api_key="k")

    def test_text_thought_and_usage(self) -> None:
        answer = gemini_generate.parse(
            self.route,
            {
                "responseId": "r1",
                "modelVersion": "gemini-2.5-pro-001",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "thinking...", "thought": True},
                                {"text": "Answer"},
                                {"text": " here"},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 30,
                    "candidatesTokenCount": 10,
                    "thoughtsTokenCount": 6,
                    "cachedContentTokenCount": 12,
                    "totalTokenCount": 46,
                },
            },
        )
        choice = answer["choices"][0]  # type: ignore[index]
        assert choice["message"] == {"role": "assistant", "content": "Answer here", "reasoning_content": "thinking..."}
        assert choice["finish_reason"] == "stop"
        assert answer["id"] == "r1"
        assert answer["usage"] == {
            "prompt_tokens": 30,
            "completion_tokens": 16,
            "total_tokens": 46,
            "prompt_tokens_details": {"cached_tokens": 12},
            "completion_tokens_details": {"reasoning_tokens": 6},
        }

    def test_function_call_becomes_a_tool_call_that_keeps_the_thought_signature_in_its_id(self) -> None:
        answer = gemini_generate.parse(
            self.route,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {"name": "lookup", "args": {"city": "Paris"}},
                                    "thoughtSignature": "SIG",
                                }
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )
        choice = answer["choices"][0]  # type: ignore[index]
        (call,) = choice["message"]["tool_calls"]
        assert call["id"].endswith("__thought__SIG")
        assert call["function"] == {"name": "lookup", "arguments": '{"city": "Paris"}'}
        assert choice["finish_reason"] == "tool_calls"

    @pytest.mark.parametrize(
        ("reason", "finish"),
        [
            ("STOP", "stop"),
            ("MAX_TOKENS", "length"),
            ("SAFETY", "content_filter"),
            ("RECITATION", "content_filter"),
            (None, "stop"),
        ],
    )
    def test_finish_reason_mapping(self, reason: str | None, finish: str) -> None:
        candidate: Payload = {"content": {"parts": [{"text": "x"}]}}
        if reason:
            candidate["finishReason"] = reason
        answer = gemini_generate.parse(self.route, {"candidates": [candidate]})
        assert answer["choices"][0]["finish_reason"] == finish  # type: ignore[index]

    def test_a_blocked_prompt_is_a_content_filter_finish(self) -> None:
        answer = gemini_generate.parse(self.route, {"promptFeedback": {"blockReason": "SAFETY"}})
        assert answer["choices"][0]["finish_reason"] == "content_filter"  # type: ignore[index]


class TestGeminiStream:
    route = resolve_route("gemini/gemini-2.5-pro", api_key="k")

    def test_text_fragments_then_a_closing_chunk_with_finish_reason_and_usage(self) -> None:
        chunks = _feed(
            gemini_generate.decoder(self.route),
            [
                (None, {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]}),
                (None, {"candidates": [{"content": {"parts": [{"text": "lo"}]}}]}),
                (
                    None,
                    {
                        "candidates": [{"content": {"parts": [{"text": "!"}]}, "finishReason": "STOP"}],
                        "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 3, "totalTokenCount": 7},
                    },
                ),
            ],
        )
        assert [_delta(c) for c in chunks] == [{"content": "Hel"}, {"content": "lo"}, {"content": "!"}]
        assert [_finish(c) for c in chunks] == [None, None, "stop"]
        assert "usage" not in chunks[0]
        assert chunks[-1]["usage"]["prompt_tokens"] == 4  # type: ignore[index]
        assert len({c["id"] for c in chunks}) == 1

    def test_tool_calls_are_indexed_across_events_and_finish_as_tool_calls(self) -> None:
        chunks = _feed(
            gemini_generate.decoder(self.route),
            [
                (None, {"candidates": [{"content": {"parts": [{"functionCall": {"name": "a", "args": {}}}]}}]}),
                (
                    None,
                    {
                        "candidates": [
                            {
                                "content": {"parts": [{"functionCall": {"name": "b", "args": {"k": 1}}}]},
                                "finishReason": "STOP",
                            }
                        ]
                    },
                ),
            ],
        )
        calls = [call for c in chunks for call in _delta(c)["tool_calls"]]  # type: ignore[union-attr]
        assert [(c["index"], c["function"]["name"]) for c in calls] == [(0, "a"), (1, "b")]
        assert _finish(chunks[-1]) == "tool_calls"

    def test_thought_parts_stream_as_reasoning_content(self) -> None:
        chunks = _feed(
            gemini_generate.decoder(self.route),
            [(None, {"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": "ok"}]}}]})],
        )
        assert _delta(chunks[0]) == {"reasoning_content": "hmm", "content": "ok"}

    def test_an_empty_event_yields_nothing(self) -> None:
        assert _feed(gemini_generate.decoder(self.route), [(None, {"candidates": [{"content": {"parts": []}}]})]) == []

    def test_an_error_event_raises(self) -> None:
        with pytest.raises(LLMStreamError):
            _feed(gemini_generate.decoder(self.route), [(None, {"error": {"code": 429, "message": "quota"}})])


class TestOllama:
    route = resolve_route("ollama/llama3.1", api_base="http://localhost:11434")

    def test_parse_text_thinking_tool_calls_and_counts(self) -> None:
        answer = ollama_chat.parse(
            self.route,
            {
                "model": "llama3.1",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "reasoning",
                    "tool_calls": [{"function": {"name": "get_time", "arguments": {"tz": "UTC"}}}],
                },
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 11,
                "eval_count": 4,
            },
        )
        choice = answer["choices"][0]  # type: ignore[index]
        message = choice["message"]
        assert message["content"] is None
        assert message["reasoning_content"] == "reasoning"
        (call,) = message["tool_calls"]
        assert call["function"] == {"name": "get_time", "arguments": '{"tz": "UTC"}'}
        assert choice["finish_reason"] == "tool_calls"
        assert answer["usage"] == {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}

    @pytest.mark.parametrize(("done_reason", "finish"), [("stop", "stop"), ("length", "length"), (None, "stop")])
    def test_parse_finish_reason(self, done_reason: str | None, finish: str) -> None:
        answer = ollama_chat.parse(self.route, {"message": {"content": "x"}, "done": True, "done_reason": done_reason})
        assert answer["choices"][0]["finish_reason"] == finish  # type: ignore[index]

    def test_stream_fragments_then_the_done_line_with_counts(self) -> None:
        chunks = _feed(
            ollama_chat.decoder(self.route),
            [
                (None, {"message": {"role": "assistant", "content": "Hel"}, "done": False}),
                (None, {"message": {"role": "assistant", "thinking": "t"}, "done": False}),
                (
                    None,
                    {
                        "message": {"role": "assistant", "content": ""},
                        "done": True,
                        "done_reason": "length",
                        "prompt_eval_count": 5,
                        "eval_count": 2,
                    },
                ),
            ],
        )
        assert [_delta(c) for c in chunks] == [{"content": "Hel"}, {"reasoning_content": "t"}, {}]
        assert [_finish(c) for c in chunks] == [None, None, "length"]
        assert chunks[-1]["usage"] == {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}

    def test_stream_tool_calls_count_across_lines(self) -> None:
        chunks = _feed(
            ollama_chat.decoder(self.route),
            [
                (None, {"message": {"tool_calls": [{"function": {"name": "a", "arguments": {}}}]}, "done": False}),
                (None, {"message": {"tool_calls": [{"function": {"name": "b", "arguments": {}}}]}, "done": False}),
                (None, {"message": {}, "done": True}),
            ],
        )
        calls = [call for c in chunks for call in _delta(c).get("tool_calls", [])]  # type: ignore[union-attr]
        assert [c["index"] for c in calls] == [0, 1]
        assert _finish(chunks[-1]) == "tool_calls"

    def test_an_error_line_raises(self) -> None:
        with pytest.raises(LLMStreamError):
            _feed(ollama_chat.decoder(self.route), [(None, {"error": "model 'x' not found"})])


class TestOpenAIChatDecoder:
    route = resolve_route("openai/gpt-4o", api_key="k")

    def test_chunks_pass_through_untouched_until_done(self) -> None:
        first = {"choices": [{"index": 0, "delta": {"content": "a"}, "finish_reason": None}]}
        usage = {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        decoder = openai_chat.decoder(self.route)
        chunks = _feed(decoder, [(None, first), (None, usage), (None, "[DONE]"), (None, first)])
        assert chunks == [first, usage]
        assert decoder.done

    def test_an_error_object_without_choices_raises(self) -> None:
        with pytest.raises(LLMStreamError):
            _feed(openai_chat.decoder(self.route), [(None, {"error": {"message": "boom", "code": 500}})])

    def test_a_chunk_with_choices_and_an_error_field_is_not_an_error(self) -> None:
        chunk = {"error": None, "choices": [{"index": 0, "delta": {"content": "x"}}]}
        assert _feed(openai_chat.decoder(self.route), [(None, chunk)]) == [chunk]

    @pytest.mark.parametrize("data", ["", ": keep-alive", "{broken", "[1]"])
    def test_garbage_is_skipped(self, data: str) -> None:
        assert _feed(openai_chat.decoder(self.route), [(None, data)]) == []

    def test_parse_returns_the_provider_answer_itself(self) -> None:
        payload: Payload = {"choices": [{"message": {"content": "x"}}]}
        assert openai_chat.parse(self.route, payload) is payload

    def test_deepseek_cache_hits_are_reported_where_usage_readers_look(self) -> None:
        payload: Payload = {
            "choices": [{"message": {"content": "x"}}],
            "usage": {"prompt_tokens": 100, "prompt_cache_hit_tokens": 64, "prompt_cache_miss_tokens": 36},
        }
        usage = openai_chat.parse(self.route, payload)["usage"]
        assert isinstance(usage, dict)
        assert usage["prompt_tokens_details"] == {"cached_tokens": 64}
        assert usage["prompt_cache_hit_tokens"] == 64

    def test_deepseek_cache_hits_are_reported_on_the_final_stream_chunk(self) -> None:
        final = {"choices": [], "usage": {"prompt_tokens": 10, "prompt_cache_hit_tokens": 8}}
        (chunk,) = _feed(openai_chat.decoder(self.route), [(None, final)])
        usage = chunk["usage"]
        assert isinstance(usage, dict)
        assert usage["prompt_tokens_details"] == {"cached_tokens": 8}

    def test_anthropic_style_cache_reads_from_a_gateway_are_reported_too(self) -> None:
        payload: Payload = {"usage": {"prompt_tokens": 100, "cache_read_input_tokens": 30}}
        usage = openai_chat.parse(self.route, payload)["usage"]
        assert isinstance(usage, dict)
        assert usage["prompt_tokens_details"] == {"cached_tokens": 30}

    def test_an_existing_cached_count_is_not_overwritten(self) -> None:
        payload: Payload = {
            "usage": {"prompt_cache_hit_tokens": 5, "prompt_tokens_details": {"cached_tokens": 40, "audio_tokens": 0}}
        }
        usage = openai_chat.parse(self.route, payload)["usage"]
        assert isinstance(usage, dict)
        assert usage["prompt_tokens_details"] == {"cached_tokens": 40, "audio_tokens": 0}

    def test_a_zero_cached_count_is_filled_in_from_the_deepseek_field(self) -> None:
        payload: Payload = {"usage": {"prompt_cache_hit_tokens": 7, "prompt_tokens_details": {"cached_tokens": 0}}}
        usage = openai_chat.parse(self.route, payload)["usage"]
        assert isinstance(usage, dict)
        assert usage["prompt_tokens_details"] == {"cached_tokens": 7}

    @pytest.mark.parametrize("hits", [0, -3, True, "64", None])
    def test_unusable_hit_counts_leave_usage_untouched(self, hits: object) -> None:
        payload: Payload = {"usage": {"prompt_tokens": 9, "prompt_cache_hit_tokens": hits}}
        usage = openai_chat.parse(self.route, payload)["usage"]
        assert isinstance(usage, dict)
        assert "prompt_tokens_details" not in usage


class TestResponsesDecoder:
    route = resolve_route("openai/gpt-5", api_key="k")

    @pytest.mark.parametrize("terminal", ["response.completed", "response.failed", "response.incomplete"])
    def test_terminal_events_end_the_stream_after_being_delivered(self, terminal: str) -> None:
        decoder = openai_responses.decoder(self.route)
        delta = {"type": "response.output_text.delta", "delta": "hi"}
        end = {"type": terminal, "response": {"id": "r"}}
        chunks = _feed(decoder, [(None, delta), (None, end), (None, delta)])
        assert chunks == [delta, end]
        assert decoder.done

    def test_an_untyped_error_object_raises(self) -> None:
        with pytest.raises(LLMStreamError):
            _feed(openai_responses.decoder(self.route), [(None, {"error": {"message": "boom"}})])

    def test_the_event_header_names_the_type_when_the_payload_has_none(self) -> None:
        decoder = openai_responses.decoder(self.route)
        chunks = _feed(decoder, [("response.completed", {"response": {"id": "r"}})])
        assert chunks == [{"response": {"id": "r"}}]
        assert decoder.done
