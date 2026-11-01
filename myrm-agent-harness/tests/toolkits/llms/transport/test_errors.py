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
            ({"error": {"code": 429, "message": "quota"}}, 429),
            ({"error": {"code": "503"}}, 503),
            ({"code": 500}, 500),
            ({"error": {"code": "rate_limit_exceeded"}}, None),
            ({"error": {"code": 200}}, None),
            ({"error": "plain text"}, None),
        ],
    )
    def test_status_comes_only_from_a_numeric_error_code(self, payload: dict[str, object], status: int | None) -> None:
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
            (
                400,
                '{"error": {"message": "This model\'s maximum context length is 8192 tokens", "code": "context_length_exceeded"}}',
                ErrorKind.CONTEXT_OVERFLOW,
            ),
            (404, '{"error": {"message": "The model `gpt-9` does not exist", "code": "model_not_found"}}', ErrorKind.MODEL_NOT_FOUND),
        ],
    )
    def test_http_failures_classify_by_status_and_text(self, status: int, body: str, kind: ErrorKind) -> None:
        assert classify_error(self._error(status, body)) == kind

    def test_a_stream_error_with_a_numeric_code_classifies_like_the_http_failure(self) -> None:
        error = LLMStreamError("openrouter", {"error": {"code": 429, "message": "Rate limit exceeded"}})
        assert classify_error(error) == ErrorKind.RATE_LIMIT
