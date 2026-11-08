"""What a failed Responses answer or event turns into, and the usage a Responses answer reports.

An ``error`` event ends the answer where the provider broke it: read as an ordinary event, the call would return the
half answer as a success. The failure carries the status it stands for, so the agent repeats a provider fault and
leaves a rejected request alone.
"""

from __future__ import annotations

from typing import Any

import pytest

from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import (
    ResponsesStreamError,
    assert_responses_payload_not_failed,
    responses_dict_to_chat_completion,
    responses_stream_failure,
)
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error

Event = dict[str, Any]
_FAILED_RESPONSE: Event = {"status": "failed", "error": {"code": "server_error", "message": "boom"}}


class TestStreamFailure:
    @pytest.mark.parametrize(
        ("event", "message", "status"),
        [
            # OpenAI's own error event: code and message sit on the event.
            (
                {"type": "error", "code": "server_error", "message": "boom", "param": None, "sequence_number": 2},
                "server_error: boom",
                500,
            ),
            ({"type": "error", "code": "rate_limit_exceeded", "message": "slow down", "sequence_number": 2}, None, 429),
            ({"type": "error", "code": "ERR_SOMETHING", "message": "Something went wrong"}, None, 500),
            ({"type": "error", "message": "boom"}, "boom", 500),
            ({"type": "response.error", "message": "boom"}, "boom", 500),
            # A gateway nests the same object in ``error``.
            ({"type": "error", "error": {"message": "x", "type": "rate_limit_exceeded"}}, "x", 429),
            ({"type": "error", "error": {"code": 503, "message": "unavailable"}}, "unavailable", 503),
            ({"type": "error", "error": "plain text"}, "plain text", 500),
            ({"type": "response.failed", "response": _FAILED_RESPONSE}, "server_error: boom", 500),
            ({"type": "response.failed", "error": {"message": "boom"}}, "boom", 500),
            ({"type": "response.completed", "response": _FAILED_RESPONSE}, "server_error: boom", 500),
            (
                {"type": "response.failed", "response": {"error": {"code": "rate_limit_exceeded", "message": "x"}}},
                "rate_limit_exceeded: x",
                429,
            ),
            # Nothing more is said: the event is still the end of the answer.
            ({"type": "error"}, "Responses API request failed", 500),
            ({"type": "error", "code": "server_error"}, "Responses API request failed", 500),
            ({"type": "response.failed"}, "Responses API request failed", 500),
            ({"type": "response.failed", "response": {"status": "failed"}}, "Responses API request failed", 500),
            ({"type": "response.completed", "response": {"status": "failed"}}, "Responses API request failed", 500),
        ],
    )
    def test_an_event_that_reports_a_failure_raises_with_the_status_it_stands_for(
        self, event: Event, message: str | None, status: int
    ) -> None:
        failure = responses_stream_failure(event)

        assert isinstance(failure, ResponsesStreamError)
        assert failure.status_code == status
        if message is not None:
            assert str(failure) == message

    @pytest.mark.parametrize(
        "event",
        [
            {"type": "response.output_text.delta", "delta": "x"},
            {"type": "response.created", "response": {"status": "in_progress", "usage": None}},
            {"type": "response.completed", "response": {"status": "completed", "error": None}},
            {"type": "response.incomplete", "response": {"status": "incomplete"}},
            {"type": "response.output_text.delta", "delta": "x", "error": None},
            # An MCP tool call that failed is the model's to see, not the end of the answer.
            {"type": "response.mcp_call.failed", "item_id": "mcp_1"},
            {"type": "response.function_call_arguments.delta", "delta": "{"},
            {},
        ],
    )
    def test_an_event_that_is_not_a_failure_is_not_one(self, event: Event) -> None:
        assert responses_stream_failure(event) is None

    @pytest.mark.parametrize(
        ("event", "kind"),
        [
            ({"type": "error", "code": "server_error", "message": "boom"}, ErrorKind.OVERLOADED),
            ({"type": "error", "code": "rate_limit_exceeded", "message": "slow"}, ErrorKind.RATE_LIMIT),
            ({"type": "response.failed", "response": _FAILED_RESPONSE}, ErrorKind.OVERLOADED),
            ({"type": "error", "message": "unnamed fault"}, ErrorKind.OVERLOADED),
        ],
    )
    def test_the_agent_repeats_a_provider_fault_and_waits_out_a_rate_limit(self, event: Event, kind: ErrorKind) -> None:
        failure = responses_stream_failure(event)

        assert failure is not None
        assert classify_error(failure) == kind


class TestFailedPayload:
    @pytest.mark.parametrize(
        ("payload", "status"),
        [
            ({"status": "failed", "error": {"code": "server_error", "message": "boom"}}, 500),
            ({"status": "failed", "error": {"code": "rate_limit_exceeded", "message": "x"}}, 429),
            # The whole answer names nothing: it stays unknown, as a request answered with such a body always was.
            ({"status": "failed", "error": {"message": "unnamed"}}, None),
            ({"status": "failed", "error": {"code": "billing_required", "message": "Insufficient credits"}}, None),
            ({"status": "failed"}, None),
            ({"status": "failed", "error": None}, None),
        ],
    )
    def test_a_failed_response_raises_with_the_status_its_code_implies(
        self, payload: Event, status: int | None
    ) -> None:
        with pytest.raises(ResponsesStreamError) as caught:
            assert_responses_payload_not_failed(payload)

        assert caught.value.status_code == status

    @pytest.mark.parametrize("status", ["completed", "incomplete", "in_progress", None])
    def test_any_other_status_is_not_a_failure(self, status: str | None) -> None:
        assert_responses_payload_not_failed({"status": status, "error": {"message": "stale"}})

    def test_a_server_fault_is_repeated(self) -> None:
        with pytest.raises(ResponsesStreamError) as caught:
            assert_responses_payload_not_failed({"status": "failed", "error": {"code": "server_error", "message": "x"}})

        assert classify_error(caught.value) == ErrorKind.OVERLOADED


class TestUsage:
    @staticmethod
    def _usage(usage: object) -> object:
        return responses_dict_to_chat_completion({"output": [], "usage": usage})["usage"]

    @pytest.mark.parametrize("usage", [None, {}, "n/a", [], 0])
    def test_an_answer_without_usable_usage_has_an_empty_one_and_not_none(self, usage: object) -> None:
        assert self._usage(usage) == {}

    def test_an_answer_without_a_usage_field_has_an_empty_one(self) -> None:
        assert responses_dict_to_chat_completion({"output": []})["usage"] == {}

    @pytest.mark.parametrize(
        ("usage", "counts"),
        [
            ({"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}, (11, 7, 18)),
            ({"input_tokens": "11", "output_tokens": "7"}, (11, 7, 18)),
            ({"input_tokens": 11.0, "output_tokens": 7.9}, (11, 7, 18)),
            ({"prompt_tokens": 11, "completion_tokens": 7}, (11, 7, 18)),
            ({"input_tokens": 11}, (11, 0, 11)),
            ({"input_tokens": 11, "output_tokens": 7, "total_tokens": 99}, (11, 7, 99)),
            # What is not a count is zero, and the total is the sum of what is.
            ({"input_tokens": "n/a", "output_tokens": [], "total_tokens": {}}, (0, 0, 0)),
            ({"input_tokens": None, "output_tokens": None, "total_tokens": None}, (0, 0, 0)),
            ({"input_tokens": -5, "output_tokens": 7}, (0, 7, 7)),
            ({"input_tokens": 11, "output_tokens": 7, "total_tokens": "n/a"}, (11, 7, 18)),
            ({"input_tokens": 11, "output_tokens": 7, "total_tokens": -3}, (11, 7, 18)),
        ],
    )
    def test_counts_are_read_whatever_way_the_provider_wrote_them(
        self, usage: Event, counts: tuple[int, int, int]
    ) -> None:
        assert self._usage(usage) == dict(
            zip(("prompt_tokens", "completion_tokens", "total_tokens"), counts, strict=True)
        )
