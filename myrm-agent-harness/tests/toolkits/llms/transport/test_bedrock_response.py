"""Bedrock Converse answers: a ``converse`` body and a ``converse-stream`` event sequence read as chat completions.

The answer comes back in the chat.completion shape the adapter already consumes, with Bedrock's cache counters folded
into the prompt total, so these tests pin the shape (content, reasoning, tool calls, usage, finish reason) and the
failures: an exception inside an open stream is the provider's own failure, a cut-off one is a retryable answer error.
"""

from __future__ import annotations

import json
import re

import pytest

from myrm_agent_harness.toolkits.llms.transport import bedrock_response
from myrm_agent_harness.toolkits.llms.transport.bedrock_content import encode_tool_name
from myrm_agent_harness.toolkits.llms.transport.bedrock_response import BedrockStreamDecoder
from myrm_agent_harness.toolkits.llms.transport.bedrock_structured import JSON_TOOL
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError, LLMResponseError
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Body = dict[str, object]
ROUTE = resolve_route("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", api_key="k")
USAGE: Body = {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}


def _answer(*blocks: Body, reason: object = "end_turn", usage: object = None) -> Body:
    body: Body = {"output": {"message": {"role": "assistant", "content": list(blocks)}}, "stopReason": reason}
    if usage is not None:
        body["usage"] = usage
    return body


def _message(body: Body) -> Body:
    choice = body["choices"][0]  # type: ignore[index]
    return choice["message"]  # type: ignore[no-any-return]


def _finish(body: Body) -> object:
    return body["choices"][0]["finish_reason"]  # type: ignore[index]


def _call(tool_use_id: str, name: str, arguments: object) -> Body:
    return {"toolUse": {"toolUseId": tool_use_id, "name": name, "input": arguments}}


class TestAnswer:
    def test_text_blocks_are_the_content_and_the_answer_is_a_chat_completion(self) -> None:
        body = bedrock_response.parse(ROUTE, _answer({"text": "Hello, "}, {"text": "world"}, usage=USAGE))
        assert _message(body) == {"role": "assistant", "content": "Hello, world"}
        assert (body["object"], body["model"]) == ("chat.completion", ROUTE.model)
        assert _finish(body) == "stop"

    def test_every_answer_gets_its_own_id(self) -> None:
        first, second = (bedrock_response.parse(ROUTE, _answer({"text": "x"})) for _ in range(2))
        assert re.fullmatch(r"chatcmpl-[0-9a-f]{32}", str(first["id"]))
        assert first["id"] != second["id"]

    def test_an_answer_without_content_has_null_content(self) -> None:
        assert _message(bedrock_response.parse(ROUTE, _answer()))["content"] is None

    def test_blocks_the_adapter_has_no_use_for_are_ignored(self) -> None:
        blocks: list[object] = [{"guardContent": {}}, {"citationsContent": {}}, "junk", 5, {"text": "kept"}]
        body = bedrock_response.parse(ROUTE, {"output": {"message": {"content": blocks}}, "stopReason": "end_turn"})
        assert _message(body)["content"] == "kept"

    def test_a_tool_call_keeps_the_providers_id_and_its_arguments_as_json_text(self) -> None:
        body = bedrock_response.parse(
            ROUTE,
            _answer({"text": "Checking"}, _call("tooluse_1", "get_weather", {"city": "Paris"}), reason="tool_use"),
        )
        message = _message(body)
        assert message["content"] == "Checking"
        assert message["tool_calls"] == [
            {
                "id": "tooluse_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            }
        ]
        assert _finish(body) == "tool_calls"

    def test_arguments_keep_their_characters_and_a_missing_object_is_an_empty_one(self) -> None:
        body = bedrock_response.parse(
            ROUTE, _answer(_call("1", "t", {"city": "東京"}), _call("2", "t", None), reason="tool_use")
        )
        calls = _message(body)["tool_calls"]
        assert [c["function"]["arguments"] for c in calls] == ['{"city": "東京"}', "{}"]  # type: ignore[index]

    def test_a_tool_name_comes_back_as_the_agent_registered_it(self) -> None:
        body = bedrock_response.parse(ROUTE, _answer(_call("1", encode_tool_name("web.search"), {}), reason="tool_use"))
        assert _message(body)["tool_calls"][0]["function"]["name"] == "web.search"  # type: ignore[index]

    def test_reasoning_is_text_for_the_reader_and_signed_blocks_for_the_replay(self) -> None:
        thought = {"reasoningContent": {"reasoningText": {"text": "hm", "signature": "sig"}}}
        unsigned = {"reasoningContent": {"reasoningText": {"text": "ok"}}}
        redacted = {"reasoningContent": {"redactedContent": "QUJD"}}
        message = _message(bedrock_response.parse(ROUTE, _answer(thought, unsigned, redacted, {"text": "answer"})))
        assert message["reasoning_content"] == "hmok"
        assert message["thinking_blocks"] == [
            {"type": "thinking", "thinking": "hm", "signature": "sig"},
            {"type": "thinking", "thinking": "ok"},
            {"type": "redacted_thinking", "data": "QUJD"},
        ]
        assert message["content"] == "answer"

    def test_an_answer_without_a_message_is_a_response_error_the_caller_can_retry(self) -> None:
        for payload in ({}, {"output": {}}, {"output": {"message": {"content": "text"}}}, {"output": []}):
            with pytest.raises(LLMResponseError, match="without a message"):
                bedrock_response.parse(ROUTE, payload)


class TestUsage:
    def test_the_counts_are_the_providers_and_the_total_is_the_providers_total(self) -> None:
        usage = bedrock_response.parse(ROUTE, _answer({"text": "x"}, usage=USAGE))["usage"]
        assert (usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"]) == (10, 5, 15)  # type: ignore[index]

    def test_a_total_that_is_not_the_sum_of_the_counts_stays_the_providers(self) -> None:
        usage = {"inputTokens": 10, "outputTokens": 5, "totalTokens": 99}
        assert bedrock_response.parse(ROUTE, _answer({"text": "x"}, usage=usage))["usage"]["total_tokens"] == 99  # type: ignore[index]

    def test_cache_reads_and_writes_count_toward_the_prompt_like_every_other_provider_reports_it(self) -> None:
        cached = {
            "inputTokens": 10,
            "outputTokens": 5,
            "totalTokens": 25,
            "cacheReadInputTokens": 6,
            "cacheWriteInputTokens": 4,
        }
        assert bedrock_response.parse(ROUTE, _answer({"text": "x"}, usage=cached))["usage"] == {
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "prompt_tokens_details": {"cached_tokens": 6},
            "cache_creation_input_tokens": 4,
            "cache_read_input_tokens": 6,
        }

    def test_a_missing_total_is_the_sum_of_the_counts(self) -> None:
        usage = bedrock_response.parse(ROUTE, _answer({"text": "x"}, usage={"inputTokens": 3, "outputTokens": 4}))[
            "usage"
        ]
        assert usage["total_tokens"] == 7  # type: ignore[index]

    @pytest.mark.parametrize("junk", [None, "12", -3, True, 1.5, [1]])
    def test_a_count_that_is_no_positive_integer_is_zero(self, junk: object) -> None:
        parsed = bedrock_response.parse(
            ROUTE, _answer({"text": "x"}, usage={"inputTokens": junk, "outputTokens": junk})
        )
        assert (parsed["usage"]["prompt_tokens"], parsed["usage"]["completion_tokens"]) == (0, 0)  # type: ignore[index]

    @pytest.mark.parametrize("usage", [None, [], "x"])
    def test_an_answer_without_usage_is_still_an_answer(self, usage: object) -> None:
        assert bedrock_response.parse(ROUTE, _answer({"text": "x"}, usage=usage))["usage"] == {}


class TestFinishReason:
    @pytest.mark.parametrize(
        ("reason", "finish"),
        [
            ("end_turn", "stop"),
            ("stop_sequence", "stop"),
            ("max_tokens", "length"),
            ("model_context_window_exceeded", "length"),
            ("content_filtered", "content_filter"),
            ("guardrail_intervened", "content_filter"),
            ("something_new", "stop"),
        ],
    )
    def test_the_providers_word_is_mapped(self, reason: str, finish: str) -> None:
        assert _finish(bedrock_response.parse(ROUTE, _answer({"text": "x"}, reason=reason))) == finish

    def test_tool_use_is_tool_calls_only_when_the_caller_has_calls_to_run(self) -> None:
        assert _finish(bedrock_response.parse(ROUTE, _answer(_call("1", "t", {}), reason="tool_use"))) == "tool_calls"
        assert _finish(bedrock_response.parse(ROUTE, _answer({"text": "x"}, reason="tool_use"))) == "stop"

    def test_an_answer_that_names_no_stop_reason_has_no_finish_reason(self) -> None:
        assert _finish(bedrock_response.parse(ROUTE, _answer({"text": "x"}, reason=None))) is None


class TestStructuredAnswer:
    def test_the_call_of_the_json_tool_is_the_content_and_no_tool_call(self) -> None:
        body = bedrock_response.parse(ROUTE, _answer(_call("j", JSON_TOOL, {"a": "x"}), reason="tool_use"))
        message = _message(body)
        assert message["content"] == '{"a": "x"}'
        assert "tool_calls" not in message
        assert _finish(body) == "stop"

    @pytest.mark.parametrize(
        ("arguments", "content"),
        [
            ({"properties": {"a": "x"}}, '{"a": "x"}'),
            ({"properties": {"a": "x"}, "other": 1}, '{"properties": {"a": "x"}, "other": 1}'),
            ({"properties": 5}, "5"),
            ({"a": {"properties": {"b": 1}}}, '{"a": {"properties": {"b": 1}}}'),
        ],
    )
    def test_a_lone_properties_wrapper_is_removed_and_nothing_else(self, arguments: Body, content: str) -> None:
        body = bedrock_response.parse(ROUTE, _answer(_call("j", JSON_TOOL, arguments), reason="tool_use"))
        assert _message(body)["content"] == content

    def test_text_the_model_wrote_around_it_stays_in_front(self) -> None:
        body = bedrock_response.parse(
            ROUTE, _answer({"text": "Here: "}, _call("j", JSON_TOOL, {"a": 1}), reason="tool_use")
        )
        assert _message(body)["content"] == 'Here: {"a": 1}'

    def test_beside_a_real_call_the_structured_answer_is_text_and_the_call_still_runs(self) -> None:
        body = bedrock_response.parse(
            ROUTE, _answer(_call("j", JSON_TOOL, {"a": 1}), _call("t", "get_weather", {}), reason="tool_use")
        )
        message = _message(body)
        assert message["content"] == '{"a": 1}'
        assert [c["function"]["name"] for c in message["tool_calls"]] == ["get_weather"]  # type: ignore[attr-defined,union-attr]
        assert _finish(body) == "tool_calls"


# --- stream ----------------------------------------------------------------------------------------------------


def _decoder() -> BedrockStreamDecoder:
    decoder = bedrock_response.decoder(ROUTE)
    assert isinstance(decoder, BedrockStreamDecoder)
    return decoder


def _event(kind: str, **body: object) -> tuple[str, str]:
    return kind, json.dumps(body)


def _play(*events: tuple[str, str]) -> list[Body]:
    """Every chunk the decoder hands out for ``events``, then the chunks it adds when the body ends."""
    decoder = _decoder()
    chunks: list[Body] = []
    for kind, data in events:
        chunks.extend(decoder.feed(kind, data))
    chunks.extend(decoder.finish())
    return chunks


def _delta(chunk: Body) -> Body:
    return chunk["choices"][0]["delta"]  # type: ignore[index,no-any-return]


def _tool_start(index: int, tool_use_id: str, name: str) -> tuple[str, str]:
    return _event(
        "contentBlockStart", contentBlockIndex=index, start={"toolUse": {"toolUseId": tool_use_id, "name": name}}
    )


def _tool_input(index: int, text: str) -> tuple[str, str]:
    return _event("contentBlockDelta", contentBlockIndex=index, delta={"toolUse": {"input": text}})


def _stop(index: int) -> tuple[str, str]:
    return _event("contentBlockStop", contentBlockIndex=index)


def _text(index: int, text: str) -> tuple[str, str]:
    return _event("contentBlockDelta", contentBlockIndex=index, delta={"text": text})


_END = [_event("messageStop", stopReason="end_turn"), _event("metadata", usage=USAGE)]


class TestStream:
    def test_a_text_answer_is_a_role_chunk_the_text_and_a_closing_chunk_with_the_usage(self) -> None:
        chunks = _play(_event("messageStart", role="assistant"), _text(0, "Hel"), _text(0, "lo"), _stop(0), *_END)
        assert [_delta(c) for c in chunks[:3]] == [
            {"role": "assistant", "content": ""},
            {"content": "Hel"},
            {"content": "lo"},
        ]
        last = chunks[-1]
        assert last["choices"][0]["finish_reason"] == "stop"  # type: ignore[index]
        assert last["usage"]["total_tokens"] == 15  # type: ignore[index]
        assert {c["id"] for c in chunks} == {last["id"]}
        assert all(c["object"] == "chat.completion.chunk" for c in chunks)

    def test_the_stream_is_done_when_the_usage_arrived_and_not_before(self) -> None:
        decoder = _decoder()
        for kind, data in [_event("messageStart", role="assistant"), *_END[:1]]:
            decoder.feed(kind, data)
        assert not decoder.done
        decoder.feed(*_END[1])
        assert decoder.done

    def test_a_stream_that_never_said_how_it_ended_gets_no_invented_finish(self) -> None:
        chunks = _play(_event("messageStart", role="assistant"), _text(0, "cut"))
        assert [c["choices"][0]["finish_reason"] for c in chunks] == [None, None]  # type: ignore[index]

    def test_tool_calls_are_announced_then_filled_and_numbered_from_zero(self) -> None:
        chunks = _play(
            _tool_start(0, "t1", "get_weather"),
            _tool_input(0, '{"city": '),
            _tool_input(0, '"Paris"}'),
            _stop(0),
            _tool_start(1, "t2", "get_time"),
            _tool_input(1, "{}"),
            _stop(1),
            _event("messageStop", stopReason="tool_use"),
            _event("metadata", usage=USAGE),
        )
        calls = [_delta(c)["tool_calls"][0] for c in chunks if "tool_calls" in _delta(c)]  # type: ignore[index]
        assert calls == [
            {"index": 0, "id": "t1", "type": "function", "function": {"name": "get_weather", "arguments": ""}},
            {"index": 0, "function": {"arguments": '{"city": '}},
            {"index": 0, "function": {"arguments": '"Paris"}'}},
            {"index": 1, "id": "t2", "type": "function", "function": {"name": "get_time", "arguments": ""}},
            {"index": 1, "function": {"arguments": "{}"}},
        ]
        assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"  # type: ignore[index]

    def test_a_tool_that_takes_no_arguments_still_gets_an_object_to_parse(self) -> None:
        chunks = _play(_tool_start(0, "t1", "now"), _stop(0), *_END[1:])
        assert [_delta(c)["tool_calls"][0]["function"]["arguments"] for c in chunks if "tool_calls" in _delta(c)] == [
            "",
            "{}",
        ]  # type: ignore[index]

    def test_an_empty_piece_of_arguments_is_no_chunk(self) -> None:
        chunks = _play(_tool_start(0, "t1", "get_time"), _tool_input(0, ""), _tool_input(0, "{}"), _stop(0))
        pieces = [_delta(c)["tool_calls"][0]["function"]["arguments"] for c in chunks if "tool_calls" in _delta(c)]  # type: ignore[index]
        assert pieces == ["", "{}"]  # the announcement, then the one real piece; no "{}" is added to arguments given

    def test_an_event_that_names_no_block_belongs_to_the_first(self) -> None:
        chunks = _play(
            _tool_start(0, "t1", "get_time"), _event("contentBlockDelta", delta={"toolUse": {"input": "{}"}})
        )
        pieces = [_delta(c)["tool_calls"][0]["function"]["arguments"] for c in chunks if "tool_calls" in _delta(c)]  # type: ignore[index]
        assert pieces == ["", "{}"]

    def test_a_tool_name_comes_back_as_the_agent_registered_it(self) -> None:
        chunks = _play(_tool_start(0, "t1", encode_tool_name("web.search")))
        assert _delta(chunks[0])["tool_calls"][0]["function"]["name"] == "web.search"  # type: ignore[index]

    def test_reasoning_text_is_streamed_and_its_signature_and_redactions_are_not_chunks(self) -> None:
        chunks = _play(
            _event("contentBlockDelta", contentBlockIndex=0, delta={"reasoningContent": {"text": "thinking"}}),
            _event("contentBlockDelta", contentBlockIndex=0, delta={"reasoningContent": {"signature": "sig"}}),
            _event("contentBlockDelta", contentBlockIndex=0, delta={"reasoningContent": {"redactedContent": "QUJD"}}),
            _stop(0),
        )
        assert [_delta(c) for c in chunks] == [{"reasoning_content": "thinking"}]

    def test_the_structured_answer_is_buffered_and_comes_as_text_without_its_wrapper(self) -> None:
        chunks = _play(
            _tool_start(0, "j", JSON_TOOL),
            _tool_input(0, '{"properties": {"a"'),
            _tool_input(0, ': "x"}}'),
            _stop(0),
            _event("messageStop", stopReason="tool_use"),
            _event("metadata", usage=USAGE),
        )
        assert [_delta(c) for c in chunks[:-1]] == [{"content": '{"a": "x"}'}]
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"  # type: ignore[index]

    def test_a_structured_answer_that_is_not_json_comes_through_as_the_model_wrote_it(self) -> None:
        chunks = _play(_tool_start(0, "j", JSON_TOOL), _tool_input(0, '{"a": "x'), _stop(0))
        assert [_delta(c) for c in chunks] == [{"content": '{"a": "x'}]

    def test_an_empty_structured_answer_is_no_chunk(self) -> None:
        assert _play(_tool_start(0, "j", JSON_TOOL), _stop(0)) == []

    def test_real_tools_beside_the_structured_answer_are_numbered_from_zero_and_finish_as_tool_calls(self) -> None:
        chunks = _play(
            _tool_start(0, "j", JSON_TOOL),
            _tool_input(0, '{"a": 1}'),
            _stop(0),
            _tool_start(1, "t", "get_weather"),
            _tool_input(1, "{}"),
            _stop(1),
            _event("messageStop", stopReason="tool_use"),
            _event("metadata", usage=USAGE),
        )
        assert _delta(chunks[0]) == {"content": '{"a": 1}'}
        assert _delta(chunks[1])["tool_calls"][0]["index"] == 0  # type: ignore[index]
        assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"  # type: ignore[index]

    def test_cache_counters_in_the_usage_are_folded_into_the_prompt(self) -> None:
        usage = {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 6, "cacheWriteInputTokens": 4}
        chunks = _play(_event("messageStop", stopReason="end_turn"), _event("metadata", usage=usage))
        assert chunks[-1]["usage"]["prompt_tokens"] == 20  # type: ignore[index]

    def test_events_the_adapter_has_no_use_for_are_skipped_and_odd_indexes_do_not_crash(self) -> None:
        chunks = _play(
            _event("somethingNew", x=1),
            _event("contentBlockStart", contentBlockIndex=3, start={"image": {}}),
            _event("contentBlockDelta", contentBlockIndex="x", delta="junk"),
            _event("contentBlockDelta", contentBlockIndex=9, delta={"toolUse": {"input": "{}"}}),
            _stop(9),
            ("keepalive", "not json"),
            ("keepalive", ""),
        )
        assert chunks == []

    def test_a_payload_that_opens_an_object_and_does_not_close_it_fails_the_stream(self) -> None:
        with pytest.raises(LLMResponseError, match="cut off or corrupted"):
            _decoder().feed("contentBlockDelta", '{"contentBlockIndex": 0, "delta": {"text": "x')


class TestStreamFailures:
    @pytest.mark.parametrize(
        ("name", "status"),
        [
            ("validationException", 400),
            ("modelTimeoutException", 408),
            ("modelStreamErrorException", 424),
            ("throttlingException", 429),
            ("internalServerException", 500),
            ("serviceUnavailableException", 503),
            ("accessDeniedException", 403),
            ("resourceNotFoundException", 404),
            ("modelNotReadyException", 429),
            ("modelErrorException", 424),
        ],
    )
    def test_an_exception_of_the_stream_is_a_failure_with_the_status_it_stands_for(
        self, name: str, status: int
    ) -> None:
        with pytest.raises(LLMAnswerError) as caught:
            _decoder().feed(f"exception:{name}", '{"message": "slow down"}')
        assert caught.value.status_code == status
        assert "slow down" in str(caught.value)
        assert caught.value.llm_provider == "bedrock"

    def test_an_exception_nobody_named_is_a_fault_of_the_provider(self) -> None:
        with pytest.raises(LLMAnswerError) as caught:
            _decoder().feed("exception:", "plain text, not json")
        assert caught.value.status_code == 500
        assert "plain text" in str(caught.value)

    def test_an_error_message_carries_its_code_and_text(self) -> None:
        with pytest.raises(LLMAnswerError) as caught:
            _decoder().feed("error:InternalFailure", "boom")
        assert caught.value.status_code == 500
        assert "InternalFailure" in str(caught.value) and "boom" in str(caught.value)

    def test_the_text_of_an_exception_without_a_message_field_is_kept_whole(self) -> None:
        with pytest.raises(LLMAnswerError, match="reason"):
            _decoder().feed("exception:validationException", '{"reason": "bad"}')

    def test_chunks_before_the_exception_were_already_delivered(self) -> None:
        decoder = _decoder()
        assert decoder.feed("contentBlockDelta", json.dumps({"contentBlockIndex": 0, "delta": {"text": "so far"}}))
        with pytest.raises(LLMAnswerError):
            decoder.feed("exception:throttlingException", "{}")
