"""The one pass that gives the adapter the chat.completion shape it assumes, whatever a wire or gateway sent."""

from __future__ import annotations

import copy
import math
from typing import Final

import pytest

from myrm_agent_harness.toolkits.llms.transport.chat_shape import (
    FINISH_REASONS,
    ShapedDecoder,
    shape_chunk,
    shape_completion,
    shape_usage,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError
from myrm_agent_harness.toolkits.llms.transport.http import Chunk

Payload = dict[str, object]

# What the finish-reason table of the stack this one replaced answered for every word it knew (taken from that stack's
# source), as {OpenAI's word: the words that map onto it}. Words it did not know fell back to "stop".
_PREVIOUS_STACK: Final = {
    "stop": (
        "COMPLETE ERROR FINISH_REASON_UNSPECIFIED MALFORMED_FUNCTION_CALL MALFORMED_RESPONSE STOP TOO_MANY_TOOL_CALLS "
        "end_turn eos eos_token error network_error stop stop_sequence"
    ),
    "length": "MAX_TOKENS compaction length max_tokens",
    "tool_calls": "tool_calls tool_use",
    "function_call": "function_call",
    "content_filter": (
        "BLOCKLIST ERROR_TOXIC IMAGE_PROHIBITED_CONTENT IMAGE_SAFETY LANGUAGE OTHER PROHIBITED_CONTENT RECITATION "
        "SAFETY SPII content_filter content_filtered guardrail_intervened refusal sensitive"
    ),
}
_FINISH_OF_WORD: Final = {word: finish for finish, words in _PREVIOUS_STACK.items() for word in words.split()}


def _answer(message: Payload | None = None, finish: object = "stop") -> Payload:
    fields: Payload = {"role": "assistant", "content": "hello", **(message or {})}
    return {"id": "c1", "choices": [{"index": 0, "message": fields, "finish_reason": finish}]}


def _choices(shaped: Payload) -> list[Payload]:
    choices = shaped["choices"]
    assert isinstance(choices, list)
    return choices


def _shaped_message(answer: Payload) -> Payload:
    """The message of the only choice of ``answer`` once it is shaped."""
    (choice,) = _choices(shape_completion("p", answer))
    message = choice["message"]
    assert isinstance(message, dict)
    return message


def _shaped_finish(answer: Payload) -> object:
    (choice,) = _choices(shape_completion("p", answer))
    return choice["finish_reason"]


def _chunk_of(choice: Payload) -> Payload:
    """The only choice of a stream chunk carrying ``choice``, once it is shaped."""
    (shaped,) = _choices(shape_chunk({"choices": [choice]}))
    return shaped


class TestShapeUsage:
    def test_counts_and_their_details_that_are_already_right_come_back_unchanged(self) -> None:
        usage = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "prompt_tokens_details": {"cached_tokens": 5},
            "completion_tokens_details": {"reasoning_tokens": 3},
        }

        assert shape_usage(usage) == usage

    @pytest.mark.parametrize("raw", [None, "usage", 7, [], True])
    def test_a_usage_that_is_not_an_object_has_nothing_to_read(self, raw: object) -> None:
        assert shape_usage(raw) == {}

    @pytest.mark.parametrize(
        ("value", "count"),
        [("11", 11), (" 12 ", 12), (7.9, 7), ("1e3", 1000), (-5, 0), ("-5", 0), (0, 0)],
    )
    def test_a_count_is_a_non_negative_int_however_it_was_written(self, value: object, count: int) -> None:
        assert shape_usage({"prompt_tokens": value, "completion_tokens": 1, "total_tokens": 99}) == {
            "prompt_tokens": count,
            "completion_tokens": 1,
            "total_tokens": 99,
        }

    @pytest.mark.parametrize("value", [None, True, "n/a", [], {}, math.nan, math.inf])
    def test_a_value_that_is_not_a_count_is_left_out_not_read_as_zero(self, value: object) -> None:
        shaped = shape_usage({"prompt_tokens": value, "completion_tokens": 2})

        assert shaped == {"completion_tokens": 2, "total_tokens": 2}

    @pytest.mark.parametrize(
        ("counts", "total"),
        [
            ({"prompt_tokens": 4, "completion_tokens": 3}, 7),
            ({"prompt_tokens": 4}, 4),
            ({"completion_tokens": 3}, 3),
            ({"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 10}, 10),
        ],
    )
    def test_a_missing_total_is_the_sum_of_the_counts_that_were_given(self, counts: Payload, total: int) -> None:
        assert shape_usage(counts)["total_tokens"] == total

    def test_a_usage_without_a_single_count_stays_empty(self) -> None:
        assert shape_usage({"prompt_tokens": None, "total_tokens": "n/a", "cost": 0.5}) == {"cost": 0.5}

    def test_fields_the_cost_and_cache_readers_look_at_are_kept(self) -> None:
        usage = {"prompt_tokens": 1, "cost": 0.5, "prompt_cache_hit_tokens": 3, "cache_read_input_tokens": 2}

        assert shape_usage(usage) == {**usage, "total_tokens": 1}

    def test_details_keep_the_counts_and_drop_what_is_not_one(self) -> None:
        details = {"cached_tokens": "5", "audio_tokens": None, "label": "n/a", "text_tokens": 2.0}

        shaped = shape_usage({"prompt_tokens": 1, "prompt_tokens_details": details})

        assert shaped["prompt_tokens_details"] == {"cached_tokens": 5, "text_tokens": 2}

    @pytest.mark.parametrize("details", [None, "n/a", 3, []])
    def test_details_that_are_not_an_object_are_dropped(self, details: object) -> None:
        assert "prompt_tokens_details" not in shape_usage({"prompt_tokens": 1, "prompt_tokens_details": details})

    def test_the_input_is_left_as_the_provider_sent_it(self) -> None:
        raw = {"prompt_tokens": "11", "prompt_tokens_details": {"cached_tokens": "5"}}
        before = copy.deepcopy(raw)

        shape_usage(raw)

        assert raw == before


class TestFinishReasons:
    @pytest.mark.parametrize(("word", "finish"), sorted(_FINISH_OF_WORD.items()))
    def test_every_word_the_previous_stack_knew_means_what_it_meant(self, word: str, finish: str) -> None:
        assert _shaped_finish(_answer(finish=word)) == finish

    def test_a_response_that_filled_the_context_window_is_cut_off_whoever_forwards_the_word(self) -> None:
        assert _shaped_finish(_answer(finish="model_context_window_exceeded")) == "length"

    @pytest.mark.parametrize("word", ["something_new", "Stop", "", " ", 7, None, ["stop"]])
    def test_a_word_nobody_listed_is_a_normal_end_of_the_answer(self, word: object) -> None:
        assert _shaped_finish(_answer(finish=word)) == "stop"

    def test_the_table_only_names_openais_words(self) -> None:
        assert set(FINISH_REASONS.values()) <= {"stop", "length", "tool_calls", "content_filter", "function_call"}

    @pytest.mark.parametrize("word", ["stop", None, "end_turn", "eos", "something_new"])
    def test_a_tool_call_is_what_ended_an_answer_that_calls_one(self, word: object) -> None:
        assert _shaped_finish(_answer({"tool_calls": [{"id": "call_1"}]}, finish=word)) == "tool_calls"

    @pytest.mark.parametrize("word", ["length", "max_tokens", "content_filter", "SAFETY"])
    def test_a_cut_or_filtered_answer_keeps_its_reason_whatever_it_calls(self, word: str) -> None:
        assert _shaped_finish(_answer({"tool_calls": [{"id": "call_1"}]}, finish=word)) == _FINISH_OF_WORD[word]


class TestShapeCompletion:
    def test_a_well_formed_answer_keeps_every_field_it_has(self) -> None:
        message = {"role": "assistant", "content": "hi", "refusal": None, "annotations": [{"type": "url_citation"}]}
        answer: Payload = {
            "id": "c1",
            "model": "m",
            "choices": [{"index": 0, "message": message, "finish_reason": "stop", "logprobs": None}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "system_fingerprint": "fp",
        }

        assert shape_completion("p", copy.deepcopy(answer)) == answer

    def test_shaping_twice_changes_nothing_more(self) -> None:
        raw = _answer({"role": None, "content": [{"text": "a"}]}, finish="end_turn") | {"usage": {"prompt_tokens": "2"}}
        once = shape_completion("p", raw)

        assert shape_completion("p", copy.deepcopy(once)) == once

    @pytest.mark.parametrize("role", [None, "", 0])
    def test_a_missing_role_is_the_assistant(self, role: object) -> None:
        assert _shaped_message(_answer({"role": role}))["role"] == "assistant"

    def test_a_role_that_is_there_is_kept(self) -> None:
        assert _shaped_message(_answer({"role": "developer"}))["role"] == "developer"

    def test_content_in_typed_parts_is_the_text_of_its_text_parts(self) -> None:
        parts = [
            {"type": "text", "text": "hel"},
            {"type": "image_url"},
            "stray",
            {"type": "text", "text": "lo"},
            {"text": 5},
        ]

        assert _shaped_message(_answer({"content": parts}))["content"] == "hello"

    def test_no_content_stays_none_for_a_tool_call_answer(self) -> None:
        assert _shaped_message(_answer({"content": None, "tool_calls": [{"id": "c"}]}))["content"] is None

    def test_null_tool_calls_are_dropped_and_an_empty_list_is_kept(self) -> None:
        assert "tool_calls" not in _shaped_message(_answer({"tool_calls": None}))
        assert _shaped_message(_answer({"tool_calls": []}))["tool_calls"] == []

    def test_the_position_stands_in_for_an_index_the_provider_left_out(self) -> None:
        answer: Payload = {
            "choices": [{"message": {"content": "a"}}, {"index": 7, "message": {"content": "b"}}, {"message": {}}],
        }

        assert [choice["index"] for choice in _choices(shape_completion("p", answer))] == [0, 7, 2]

    def test_what_is_not_a_choice_is_set_aside(self) -> None:
        answer: Payload = {"choices": ["nope", None, {"message": {"content": "a"}}]}

        assert len(_choices(shape_completion("p", answer))) == 1

    @pytest.mark.parametrize("usage", [None, "x", 3, [], {}])
    def test_a_usage_that_is_not_one_becomes_empty(self, usage: object) -> None:
        assert shape_completion("p", _answer() | {"usage": usage})["usage"] == {}

    def test_the_usage_is_shaped(self) -> None:
        answer = _answer() | {"usage": {"prompt_tokens": "3", "completion_tokens": None}}

        assert shape_completion("p", answer)["usage"] == {"prompt_tokens": 3, "total_tokens": 3}

    @pytest.mark.parametrize("choices", [None, [], "x", {}, [None], ["x"], [[]]], ids=repr)
    def test_an_answer_without_a_choice_is_the_providers_failure_with_what_it_said(self, choices: object) -> None:
        with pytest.raises(LLMResponseError, match=r'p answered without a choice: .*"id": "c1"') as caught:
            shape_completion("p", {"id": "c1", "choices": choices})

        assert caught.value.llm_provider == "p"
        assert caught.value.status_code == 502

    def test_the_excerpt_of_what_it_said_is_bounded(self) -> None:
        with pytest.raises(LLMResponseError) as caught:
            shape_completion("p", {"choices": None, "note": "x" * 5000})

        assert len(str(caught.value)) < 400

    @pytest.mark.parametrize("message", [None, "text", 7, []])
    def test_a_choice_without_a_message_has_nothing_to_read(self, message: object) -> None:
        with pytest.raises(LLMResponseError, match="a choice that has no message"):
            shape_completion("p", {"choices": [{"index": 0, "message": message, "finish_reason": "stop"}]})

    def test_one_choice_without_a_message_fails_the_answer_even_beside_a_good_one(self) -> None:
        with pytest.raises(LLMResponseError):
            shape_completion("p", {"choices": [{"message": {"content": "a"}}, {"finish_reason": "stop"}]})


class TestShapeChunk:
    def test_a_well_formed_chunk_keeps_every_field_it_has(self) -> None:
        chunk: Payload = {
            "id": "c1",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "a"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        assert shape_chunk(copy.deepcopy(chunk)) == chunk

    @pytest.mark.parametrize("choices", [None, "x", {}, 7])
    def test_choices_that_are_not_a_list_are_an_empty_one(self, choices: object) -> None:
        assert shape_chunk({"id": "c1", "choices": choices})["choices"] == []

    def test_a_chunk_without_choices_gets_the_empty_list_the_adapter_iterates(self) -> None:
        assert shape_chunk({"usage": {"prompt_tokens": 1}})["choices"] == []

    @pytest.mark.parametrize("delta", [None, "x", 7, []])
    def test_a_delta_that_is_not_an_object_is_an_empty_one(self, delta: object) -> None:
        assert _chunk_of({"delta": delta, "finish_reason": None})["delta"] == {}

    def test_what_is_not_a_choice_is_set_aside_and_the_position_stands_in_for_an_index(self) -> None:
        chunk = shape_chunk({"choices": [None, "x", {"delta": {"content": "a"}}, {"index": 4, "delta": {}}]})

        assert [choice["index"] for choice in _choices(chunk)] == [2, 4]

    @pytest.mark.parametrize("word", [None, "", 0])
    def test_no_finish_reason_stays_none_while_the_stream_runs(self, word: object) -> None:
        assert _chunk_of({"delta": {}, "finish_reason": word})["finish_reason"] is None

    @pytest.mark.parametrize(
        ("word", "finish"),
        [("end_turn", "stop"), ("max_tokens", "length"), ("SAFETY", "content_filter"), ("new", "stop")],
    )
    def test_a_finish_reason_is_one_of_openais(self, word: str, finish: str) -> None:
        assert _chunk_of({"delta": {}, "finish_reason": word})["finish_reason"] == finish

    def test_a_stream_that_stops_after_tool_calls_is_not_turned_into_tool_calls(self) -> None:
        # The stack this replaced reported what the provider said; the consumers read tool calls from the deltas.
        delta = {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "f", "arguments": "{}"}}]}

        choice = _chunk_of({"delta": delta, "finish_reason": "stop"})

        assert choice["finish_reason"] == "stop"
        assert choice["delta"] == delta

    def test_a_usage_is_shaped_and_one_with_nothing_in_it_is_removed(self) -> None:
        shaped = shape_chunk({"choices": [], "usage": {"prompt_tokens": "3", "completion_tokens": "4"}})
        empty = shape_chunk({"choices": [], "usage": None})
        bare = shape_chunk({"choices": []})

        assert shaped["usage"] == {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}
        assert "usage" not in empty
        assert "usage" not in bare

    def test_the_chunk_itself_is_edited_because_the_decoder_hands_it_over(self) -> None:
        chunk: Chunk = {"choices": None}

        assert shape_chunk(chunk) is chunk


class _Inner:
    """A decoder that hands over whatever it was given and records how it was driven."""

    def __init__(self, fed: list[Chunk], tail: list[Chunk]) -> None:
        self.done = False
        self.calls: list[tuple[str | None, str]] = []
        self._fed = fed
        self._tail = tail

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        self.calls.append((event, data))
        return self._fed

    def finish(self) -> list[Chunk]:
        return self._tail


class TestShapedDecoder:
    def test_every_chunk_of_feed_and_finish_is_shaped_and_the_input_reaches_the_wire_decoder(self) -> None:
        inner = _Inner([{"choices": None}], [{"choices": [{"delta": None, "finish_reason": "end_turn"}]}])
        decoder = ShapedDecoder(inner)

        fed = decoder.feed("message", "payload")
        tail = decoder.finish()

        assert inner.calls == [("message", "payload")]
        assert fed == [{"choices": []}]
        assert tail == [{"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]

    def test_no_chunk_is_no_chunk(self) -> None:
        decoder = ShapedDecoder(_Inner([], []))

        assert decoder.feed(None, "ping") == []
        assert decoder.finish() == []

    def test_the_end_of_the_stream_is_the_wire_decoders_to_declare(self) -> None:
        inner = _Inner([], [])
        decoder = ShapedDecoder(inner)
        assert decoder.done is False

        inner.done = True

        assert decoder.done is True
