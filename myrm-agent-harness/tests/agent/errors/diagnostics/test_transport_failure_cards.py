"""A failure the model transport raises is diagnosed by what the provider said, not by the transport's framing.

The transport words a failure "openai API error 429: {body}". The status digits of that framing and the numeric ``code``
of a JSON body are data the failure classifier weighs against the payload. The keyword families of the engine read a
bare 402, 403, 404 or 429 as a word of the provider, so reading them would turn a billing refusal sent with a 429 into a
rate limit, a refusal that names rate limiting and is sent with a 403 into a rejected key, and every 404 into a missing
model. A provider that put no words to its failure said only its status, and that is then read. Each case below is a
failure whose card follows from those rules.
"""

from __future__ import annotations

import json

import httpx
import pytest

from myrm_agent_harness.agent.errors.diagnostics import ErrorContext, LLMErrorDiagnostic
from myrm_agent_harness.agent.errors.diagnostics.provider_words import keyword_text
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from tests.support.provider_errors import provider_error

_ARREARS = {"error": {"code": "1113", "message": "您的账户已欠费，请充值后重试。"}}
_QUOTA = {
    "error": {
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "type": "insufficient_quota",
        "code": "insufficient_quota",
    }
}
_NO_MODEL_WORDS = {
    "a body code of 404": {"error": {"message": "No endpoints found for foo/bar-9.", "code": 404}},
    "an Azure deployment": {
        "error": {
            "code": "DeploymentNotFound",
            "message": "The API deployment for this resource does not exist. "
            "If you created the deployment within the last 5 minutes, please wait a moment and try again.",
        }
    },
    "an OpenAI model that does not exist": {
        "error": {
            "message": "The model `gpt-9` does not exist or you do not have access to it.",
            "type": "invalid_request_error",
            "code": "model_not_found",
        }
    },
    "an Anthropic model": {"type": "error", "error": {"type": "not_found_error", "message": "model: claude-9"}},
}
_WITHOUT_WORDS = {
    "an empty object": {},
    "an empty body": "",
    "a kind only": {"error": {"type": "weird"}},
}
_GATEWAY_BODIES = {
    "an nginx page": "<html><body>504 Gateway Time-out</body></html>",
    "an empty object": {},
    "a status code only": {"error": {"code": 504}},
    "a sentence without the word": {"error": {"message": "The upstream did not answer."}},
}
_LOCAL_SERVICE = ErrorContext(model_name="llama9", is_custom_endpoint=True, base_url="http://localhost:11434")


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(provider_error("openai", 429, _ARREARS), id="escaped Chinese"),
        pytest.param(provider_error("openai", 429, json.dumps(_ARREARS, ensure_ascii=False)), id="raw Chinese"),
        pytest.param(provider_error("openai", 429, _QUOTA), id="English"),
    ],
)
def test_a_billing_refusal_sent_with_a_429_is_a_billing_card(error: Exception) -> None:
    assert LLMErrorDiagnostic.diagnose(error, locale="en").error_type == "billing"


def test_a_refusal_that_names_rate_limiting_is_a_rate_limit_card_whatever_its_status() -> None:
    body = {"error": {"message": "Your request was blocked due to rate limiting. Please slow down.", "code": None}}

    assert LLMErrorDiagnostic.diagnose(provider_error("openai", 403, body), locale="en").error_type == "rate_limit"


@pytest.mark.parametrize("body", _NO_MODEL_WORDS.values(), ids=_NO_MODEL_WORDS.keys())
def test_a_404_whose_words_name_no_missing_model_is_not_a_missing_model_card(body: object) -> None:
    result = LLMErrorDiagnostic.diagnose(provider_error("openai", 404, body), locale="en")

    assert result.error_type == "unknown"
    assert "ollama" not in " ".join([result.user_message, *result.resolution_steps]).lower()


@pytest.mark.parametrize("body", _WITHOUT_WORDS.values(), ids=_WITHOUT_WORDS.keys())
def test_a_404_the_provider_put_no_words_to_is_a_model_card(body: object) -> None:
    assert LLMErrorDiagnostic.diagnose(provider_error("openai", 404, body), locale="en").error_type == "model"


@pytest.mark.parametrize("body", _GATEWAY_BODIES.values(), ids=_GATEWAY_BODIES.keys())
def test_a_504_is_a_timeout_card_whatever_the_gateway_says(body: object) -> None:
    assert LLMErrorDiagnostic.diagnose(provider_error("openai", 504, body), locale="en").error_type == "timeout"


def test_a_timeout_the_provider_reports_inside_a_stream_is_a_timeout_card() -> None:
    payload = {"type": "error", "error": {"type": "timeout_error", "message": "The upstream did not answer."}}

    error = LLMAnswerError("anthropic", payload, stream=True)

    assert LLMErrorDiagnostic.diagnose(error, locale="en").error_type == "timeout"


@pytest.mark.parametrize("status", [500, 502, 503, 529])
def test_another_server_failure_is_an_overload_card(status: int) -> None:
    assert LLMErrorDiagnostic.diagnose(provider_error("openai", status, {}), locale="en").error_type == "overloaded"


def test_a_missing_model_in_the_providers_words_is_a_model_card() -> None:
    error = provider_error("ollama", 404, {"error": "model 'llama9' not found, try pulling it first"})

    assert LLMErrorDiagnostic.diagnose(error, locale="en").error_type == "model"
    assert LLMErrorDiagnostic.diagnose(error, _LOCAL_SERVICE, locale="en").error_type == "custom_model_not_found"


def test_the_keyword_text_of_a_transport_failure_is_the_providers_sentence_alone() -> None:
    error = provider_error("openai", 429, {"error": {"message": "Slow Down", "type": "rate_limit_error", "code": 429}})

    assert keyword_text(error) == "slow down"


def test_the_keyword_text_of_a_transport_failure_without_words_carries_its_status() -> None:
    text = keyword_text(provider_error("openai", 404, {"error": {"type": "weird"}}))

    assert "weird" in text
    assert "404" in text


def test_the_keyword_text_of_another_exception_is_its_text_and_class_whatever_response_it_carries() -> None:
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    response = httpx.Response(429, json={"error": {"message": "Slow Down"}}, request=request)
    error = httpx.HTTPStatusError("Client error '429 Too Many Requests'", request=request, response=response)

    text = keyword_text(error)

    assert "too many requests" in text
    assert "httpstatuserror" in text


def test_the_keyword_text_is_bounded() -> None:
    error = provider_error("openai", 400, "x" * 10_000)

    assert len(keyword_text(error)) <= 2000
