"""Transport failures: the exception shape, and that the shared classifier reads it without a provider branch."""

from __future__ import annotations

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport.errors import (
    LLMHTTPError,
    LLMStreamError,
    araise_for_status,
    raise_for_status,
)

_URL = "https://api.example.test/v1/chat/completions"


def _response(status: int, content: str | bytes = b"", headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, content=content, headers=headers, request=httpx.Request("POST", _URL))


class TestLLMHTTPError:
    def test_carries_status_parsed_body_and_response(self) -> None:
        response = _response(429, '{"error": {"message": "slow down"}}')
        error = LLMHTTPError("openai", 429, response.text, response)
        assert error.status_code == 429
        assert error.llm_provider == "openai"
        assert error.body == {"error": {"message": "slow down"}}
        assert error.response is response
        assert "openai API error 429" in str(error)

    @pytest.mark.parametrize("text", ["<html>bad gateway</html>", "", "[1, 2]", "null"])
    def test_a_body_that_is_not_a_json_object_parses_to_an_empty_mapping(self, text: str) -> None:
        assert LLMHTTPError("p", 502, text, _response(502, text)).body == {}

    def test_the_message_is_bounded(self) -> None:
        text = "x" * 10_000
        assert len(str(LLMHTTPError("p", 500, text, _response(500, text)))) < 2100


class TestLLMStreamError:
    @pytest.mark.parametrize(
        ("payload", "status"),
        [
            # The status an event carries is the status it stands for, wherever it sits and however it is written.
            ({"error": {"code": 429, "message": "quota"}}, 429),
            ({"error": {"code": "503"}}, 503),
            ({"code": 500}, 500),
            ({"error": {"code": 429, "type": "server_error"}}, 429),
            # Without one, the kind of error says what a status would have: a rejected request or a provider fault.
            ({"error": {"type": "invalid_request_error"}}, 400),
            ({"error": {"type": "authentication_error"}}, 401),
            ({"error": {"type": "permission_error"}}, 403),
            ({"error": {"type": "not_found_error"}}, 404),
            ({"error": {"type": "request_too_large"}}, 413),
            ({"error": {"type": "rate_limit_error"}}, 429),
            ({"error": {"type": "api_error"}}, 500),
            ({"error": {"type": "timeout_error"}}, 504),
            ({"error": {"type": "overloaded_error"}}, 529),
            ({"code": "server_error"}, 500),
            ({"error": {"code": "Rate_Limit_Exceeded"}}, 429),
            ({"error": {"type": "invalid_request_error", "code": "rate_limit_exceeded"}}, 429),
            # An event that names neither is a fault of the provider, which had accepted the request.
            ({"error": {"code": 200}}, 500),
            ({"error": {"code": 600}}, 500),
            ({"error": {"code": True}}, 500),
            ({"error": {"code": "mystery", "type": "mystery"}}, 500),
            ({"error": "plain text"}, 500),
            ({}, 500),
        ],
    )
    def test_the_status_is_the_one_the_event_carries_or_its_kind_implies(
        self, payload: dict[str, object], status: int
    ) -> None:
        assert LLMStreamError("openrouter", payload).status_code == status

    def test_keeps_the_payload_as_body(self) -> None:
        payload: dict[str, object] = {"error": {"message": "boom"}}
        assert LLMStreamError("p", payload).body == payload


class TestRaiseForStatus:
    def test_success_passes_through(self) -> None:
        raise_for_status(_response(200, "{}"), "p")

    def test_failure_reads_the_body_before_raising(self) -> None:
        response = _response(400, '{"error": {"message": "bad"}}')
        with pytest.raises(LLMHTTPError) as caught:
            raise_for_status(response, "p")
        assert caught.value.body == {"error": {"message": "bad"}}
        assert caught.value.response.text == '{"error": {"message": "bad"}}'

    async def test_async_twin_raises_the_same_error(self) -> None:
        with pytest.raises(LLMHTTPError) as caught:
            await araise_for_status(_response(401, '{"error": {"message": "no key"}}'), "p")
        assert caught.value.status_code == 401

    async def test_async_success_passes_through(self) -> None:
        await araise_for_status(_response(204), "p")


class TestClassification:
    """The classifier reads ``status_code`` / ``body`` / ``response`` directly: no provider-specific branch."""

    @staticmethod
    def _error(status: int, body: str, headers: dict[str, str] | None = None) -> LLMHTTPError:
        response = _response(status, body, headers)
        return LLMHTTPError("openai", status, body, response)

    @pytest.mark.parametrize(
        ("status", "body", "kind"),
        [
            (401, '{"error": {"message": "Incorrect API key provided"}}', ErrorKind.AUTH),
            (429, '{"error": {"message": "Rate limit reached for requests"}}', ErrorKind.RATE_LIMIT),
            (503, '{"error": {"message": "The server is overloaded"}}', ErrorKind.OVERLOADED),
            (408, '{"error": {"message": "The request could not be completed"}}', ErrorKind.TIMEOUT),
            (
                400,
                '{"error": {"message": "This model\'s maximum context length is 8192 tokens", "code": "context_length_exceeded"}}',
                ErrorKind.CONTEXT_OVERFLOW,
            ),
            (
                404,
                '{"error": {"message": "The model `gpt-9` does not exist", "code": "model_not_found"}}',
                ErrorKind.MODEL_NOT_FOUND,
            ),
        ],
    )
    def test_http_failures_classify_by_status_and_text(self, status: int, body: str, kind: ErrorKind) -> None:
        assert classify_error(self._error(status, body)) == kind

    def test_a_stream_error_with_a_numeric_code_classifies_like_the_http_failure(self) -> None:
        error = LLMStreamError("openrouter", {"error": {"code": 429, "message": "Rate limit exceeded"}})
        assert classify_error(error) == ErrorKind.RATE_LIMIT

    @pytest.mark.parametrize(
        ("payload", "kind"),
        [
            # A fault of the provider is worth repeating, whichever way the wire words it.
            ({"error": {"type": "server_error", "message": "The server had an error"}}, ErrorKind.OVERLOADED),
            (
                {"type": "error", "error": {"type": "api_error", "message": "Internal server error"}},
                ErrorKind.OVERLOADED,
            ),
            ({"error": "model runner has unexpectedly stopped"}, ErrorKind.OVERLOADED),
            ({"error": {"type": "overloaded_error", "message": "Overloaded"}}, ErrorKind.OVERLOADED),
            # A rejected request or credential is not: repeating it only repeats the refusal.
            (
                {
                    "type": "error",
                    "error": {"type": "invalid_request_error", "message": "messages: roles must alternate"},
                },
                ErrorKind.FORMAT_ERROR,
            ),
            (
                {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}},
                ErrorKind.AUTH,
            ),
            # What the text says about the failure still outranks the status.
            (
                {
                    "error": {
                        "type": "insufficient_quota",
                        "message": "You exceeded your current quota, please check your plan and billing details",
                    }
                },
                ErrorKind.BILLING,
            ),
            (
                {
                    "error": {
                        "type": "invalid_request_error",
                        "code": "context_length_exceeded",
                        "message": "This model's maximum context length is 8192 tokens",
                    }
                },
                ErrorKind.CONTEXT_OVERFLOW,
            ),
        ],
    )
    def test_a_stream_error_event_classifies_like_the_same_failure_answered_with_a_status(
        self, payload: dict[str, object], kind: ErrorKind
    ) -> None:
        assert classify_error(LLMStreamError("openai", payload)) == kind
