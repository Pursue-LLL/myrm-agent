"""A failure the shared classifier recognizes is shown by its own card, whatever words the provider used.

The classifier decides what a failure is from the status code the SDK parsed as well as from the provider's wording,
while the diagnosis' keyword families read the exception text alone. litellm raises a 401 as
``AnthropicException - {"type":"error",...}`` with no status digits in it, Gemini words a rejected key as "API key not
valid" and DeepSeek words it as a 400, so those keys used to reach the user as the provider's raw JSON.
"""

from __future__ import annotations

import httpx
import httpx2
import openai
import pytest
from litellm import exceptions as litellm_errors

from myrm_agent_harness.agent.errors.diagnostics import ErrorContext, LLMErrorDiagnostic
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error

_LOCALES = ("en", "zh-CN", "zh-TW", "ja", "ko", "de")
_MODEL = "stub-model"
_PROVIDER = "stub-provider"
_BASE_URL = "https://provider.test/v1"
_CONTEXT = ErrorContext(model_name=_MODEL, is_custom_endpoint=False, base_url=_BASE_URL)
# A payload nested far past the interpreter's recursion limit, as a hostile or broken upstream could return it.
_DEEP_UPSTREAM_RAW = '{"a":' * 50_000 + "1" + "}" * 50_000


def _rejection(status: int, body: dict[str, object]) -> openai.APIStatusError:
    """The exception the OpenAI SDK raises for a response, built the way the SDK builds it."""
    response = httpx2.Response(status, request=httpx2.Request("POST", f"{_BASE_URL}/chat/completions"), json=body)
    return openai.OpenAI(api_key="stub-key", base_url=_BASE_URL)._make_status_error_from_response(response)


_ANTHROPIC_KEY_REJECTED = litellm_errors.AuthenticationError(
    message='AnthropicException - {"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}',
    model=_MODEL,
    llm_provider="anthropic",
)
_GEMINI_KEY_REJECTED = litellm_errors.AuthenticationError(
    message='GeminiException - {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", '
    '"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}',
    model=_MODEL,
    llm_provider="gemini",
)
_DEEPSEEK_KEY_REJECTED = litellm_errors.BadRequestError(
    message='DeepseekException - {"error":{"message":"Authentication Fails, Your api key: ****f4e5 is invalid",'
    '"type":"authentication_error","param":null,"code":"invalid_request_error"}}',
    model=_MODEL,
    llm_provider="deepseek",
)

# Every kind the diagnosis shows by its own card, with one failure the classifier assigns that kind and the keyword
# families cannot read.
_OWN_CARD: dict[ErrorKind, tuple[str, Exception]] = {
    ErrorKind.AUTH: ("api_key", _ANTHROPIC_KEY_REJECTED),
    ErrorKind.BILLING: ("billing", Exception("您的账户无可用资源包")),
    ErrorKind.RATE_LIMIT: (
        "rate_limit",
        litellm_errors.RateLimitError(
            message="GroqException - Please try again in 2s", model=_MODEL, llm_provider="groq"
        ),
    ),
    ErrorKind.TIMEOUT: ("timeout", RuntimeError("Server disconnected without sending a response.")),
    ErrorKind.CONTEXT_OVERFLOW: (
        "context_overflow",
        _rejection(413, {"error": {"message": "Request too large for model", "type": "invalid_request_error"}}),
    ),
    ErrorKind.RESPONSE_FORMAT_ERROR: ("response_format_error", Exception("Response is not valid JSON")),
    ErrorKind.OVERLOADED: (
        "overloaded",
        litellm_errors.ServiceUnavailableError(
            message="AnthropicException - Overloaded", model=_MODEL, llm_provider="anthropic"
        ),
    ),
    ErrorKind.SAFETY_BLOCK: ("safety_block", Exception("content_policy_violation")),
    ErrorKind.CHALLENGE_BLOCKED: (
        "challenge_blocked",
        litellm_errors.APIError(
            status_code=403,
            message="<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>cf-chl</body></html>",
            model=_MODEL,
            llm_provider=_PROVIDER,
        ),
    ),
}
# The kinds that read differently: a rejected request quotes what the provider objected to, an unrecognized failure
# quotes its own words, and a provider policy block is filed by the classifier under a missing model (a subscription
# tier gate likewise under a context overflow, which is why that kind is tested for it below). A rejected certificate
# is read by the transport family before the classifier is asked, so the engine never turns that kind into a card.
_OTHER_CARDS = {ErrorKind.FORMAT_ERROR, ErrorKind.MODEL_NOT_FOUND, ErrorKind.TLS_CERTIFICATE, ErrorKind.UNKNOWN}


def test_every_error_kind_has_a_decided_card() -> None:
    assert set(_OWN_CARD) | _OTHER_CARDS == set(ErrorKind)
    assert not set(_OWN_CARD) & _OTHER_CARDS


@pytest.mark.parametrize(
    ("kind", "expected", "exc"), [(kind, *case) for kind, case in _OWN_CARD.items()], ids=[k.value for k in _OWN_CARD]
)
def test_a_failure_the_classifier_recognizes_is_never_shown_as_unknown(
    kind: ErrorKind, expected: str, exc: Exception
) -> None:
    assert classify_error(exc) is kind

    result = LLMErrorDiagnostic.diagnose(exc, _CONTEXT, locale="en")

    assert result.error_type == expected


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize(
    "exc",
    [_ANTHROPIC_KEY_REJECTED, _GEMINI_KEY_REJECTED, _DEEPSEEK_KEY_REJECTED],
    ids=["anthropic 401", "gemini 400 api key not valid", "deepseek 401 as bad request"],
)
def test_a_rejected_key_in_the_providers_own_words_is_an_api_key_failure(exc: Exception, locale: str) -> None:
    result = LLMErrorDiagnostic.diagnose(exc, _CONTEXT, locale=locale)

    assert result.error_type == "api_key"
    assert result.locale == locale
    assert not result.user_message.startswith("[Missing")
    assert "{" not in result.user_message


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": "Request too large for model", "type": "invalid_request_error"}},
        {"error": {"message": "Payload exceeded", "type": "server_error"}},
    ],
    ids=["named as too large", "no size wording"],
)
def test_an_oversize_request_rejected_with_413_is_a_context_failure(body: dict[str, object]) -> None:
    result = LLMErrorDiagnostic.diagnose(_rejection(413, body), _CONTEXT, locale="en")

    assert result.error_type == "context_overflow"


@pytest.mark.parametrize(
    "message",
    [
        "Your organization has been disabled",
        "No endpoints available matching your guardrail restrictions and data policy",
    ],
)
def test_a_provider_policy_block_keeps_the_providers_words_instead_of_a_missing_model(message: str) -> None:
    exc = RuntimeError(message)
    assert classify_error(exc) is ErrorKind.MODEL_NOT_FOUND

    result = LLMErrorDiagnostic.diagnose(exc, _CONTEXT, locale="en")

    assert result.error_type == "unknown"
    assert message in result.user_message
    assert _MODEL not in result.user_message


def test_a_subscription_tier_gate_keeps_the_providers_words_instead_of_a_context_overflow() -> None:
    message = "Extra usage is required for long context requests."
    exc = litellm_errors.RateLimitError(
        message='AnthropicException - {"type":"error","error":{"type":"rate_limit_error","message":"' + message + '"}}',
        model=_MODEL,
        llm_provider="anthropic",
    )
    assert classify_error(exc) is ErrorKind.CONTEXT_OVERFLOW

    result = LLMErrorDiagnostic.diagnose(exc, _CONTEXT, locale="en")

    assert result.error_type == "unknown"
    assert message in result.user_message


def test_a_payload_nested_beyond_the_recursion_limit_is_still_diagnosed() -> None:
    # litellm keeps the whole payload on the response; the OpenAI SDK keeps only the inner `error` object.
    body = {"error": {"message": "Provider returned error", "metadata": {"raw": _DEEP_UPSTREAM_RAW}}}
    response = httpx.Response(400, request=httpx.Request("POST", f"{_BASE_URL}/chat/completions"), json=body)
    exc = litellm_errors.BadRequestError(
        message="Provider returned error", model=_MODEL, llm_provider=_PROVIDER, response=response
    )

    result = LLMErrorDiagnostic.diagnose(exc, _CONTEXT, locale="en")

    assert result.error_type == "format_error"
    assert "Provider returned error" in result.user_message
