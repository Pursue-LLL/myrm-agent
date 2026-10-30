"""Provider failures the shared classifier recognizes read from their own catalogue entries.

An overloaded service, a safety filter, a rejected request and a WAF challenge used to reach the end user as the
client library's raw exception text (``LLM error: litellm.ServiceUnavailableError: ...``, an HTML page for the
challenge). The diagnosis words each of them in every shipped locale, and the families the engine already knew keep
their precedence. A rejected request also tells what the provider objected to, so a mistyped model name or an invalid
parameter can be fixed from the card.
"""

from __future__ import annotations

import json

import httpx
import httpx2
import openai
import pytest
from litellm import exceptions as litellm_errors

from myrm_agent_harness.agent.errors.diagnostics import ErrorContext, LLMErrorDiagnostic

_LOCALES = ("en", "zh-CN", "zh-TW", "ja", "ko", "de")
_MODEL = "stub-model"
_LLM_PROVIDER = "stub-provider"
_CLOUDFLARE_PAGE = (
    '<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title></head><body>cf-chl</body></html>'
)
_FILTER_SENTENCE = "The response was filtered due to the prompt triggering Azure OpenAI's content management policy."
_OPENAI_REJECTION = (
    "OpenAIException - Error code: 400 - {'error': {'message': \"Invalid value: 'foo'. Supported values are: 'user'.\", "
    "'type': 'invalid_request_error', 'param': 'messages[3].role', 'code': 'invalid_value'}}"
)

_RECOGNIZED: dict[str, tuple[str, Exception]] = {
    "service unavailable": (
        "overloaded",
        litellm_errors.ServiceUnavailableError(
            message="AnthropicException - Overloaded", model=_MODEL, llm_provider=_LLM_PROVIDER
        ),
    ),
    "status 529": (
        "overloaded",
        litellm_errors.APIError(status_code=529, message="Overloaded", model=_MODEL, llm_provider=_LLM_PROVIDER),
    ),
    "safety system": (
        "safety_block",
        litellm_errors.ContentPolicyViolationError(
            message="OpenAIException - Your request was rejected as a result of our safety system. "
            "code: content_policy_violation",
            model=_MODEL,
            llm_provider=_LLM_PROVIDER,
        ),
    ),
    "content policy class": (
        "safety_block",
        litellm_errors.ContentPolicyViolationError(message=_FILTER_SENTENCE, model=_MODEL, llm_provider=_LLM_PROVIDER),
    ),
    "content filter code": (
        "safety_block",
        litellm_errors.BadRequestError(
            message='AzureException BadRequestError - {"error": {"message": "' + _FILTER_SENTENCE + '", '
            '"code": "content_filter"}}',
            model=_MODEL,
            llm_provider=_LLM_PROVIDER,
        ),
    ),
    "malformed request": (
        "format_error",
        litellm_errors.BadRequestError(
            message="OpenAIException - messages with role 'tool' must be a response to a preceeding message",
            model=_MODEL,
            llm_provider=_LLM_PROVIDER,
        ),
    ),
    "waf challenge": (
        "challenge_blocked",
        litellm_errors.APIError(status_code=403, message=_CLOUDFLARE_PAGE, model=_MODEL, llm_provider=_LLM_PROVIDER),
    ),
}


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize(("expected_type", "exc"), _RECOGNIZED.values(), ids=_RECOGNIZED.keys())
def test_a_recognized_provider_failure_has_its_own_copy(expected_type: str, exc: Exception, locale: str) -> None:
    result = LLMErrorDiagnostic.diagnose(exc, locale=locale)

    assert result.error_type == expected_type
    assert result.locale == locale
    assert result.user_message
    assert not result.user_message.startswith("[Missing")
    assert result.resolution_steps


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize(("expected_type", "exc"), _RECOGNIZED.values(), ids=_RECOGNIZED.keys())
def test_the_copy_leaks_neither_the_library_class_nor_the_provider_page(
    expected_type: str, exc: Exception, locale: str
) -> None:
    result = LLMErrorDiagnostic.diagnose(exc, locale=locale)
    visible = " ".join([result.user_message, *result.resolution_steps]).lower()

    assert "litellm" not in visible
    assert "<html" not in visible
    assert "exception" not in visible


@pytest.mark.parametrize("locale", _LOCALES)
def test_a_rejected_request_says_what_the_provider_objected_to(locale: str) -> None:
    exc = litellm_errors.BadRequestError(message=_OPENAI_REJECTION, model=_MODEL, llm_provider=_LLM_PROVIDER)

    result = LLMErrorDiagnostic.diagnose(exc, locale=locale)

    assert result.error_type == "format_error"
    assert "Invalid value: 'foo'. Supported values are: 'user'." in result.user_message
    assert not any(noise in result.user_message for noise in ("OpenAIException", "Error code", "{", "invalid_request"))


def test_prose_that_only_mentions_a_content_filter_stays_a_rejected_request() -> None:
    exc = litellm_errors.BadRequestError(
        message="OpenAIException - Unsupported value for the content filter level",
        model=_MODEL,
        llm_provider=_LLM_PROVIDER,
    )

    assert LLMErrorDiagnostic.diagnose(exc, locale="en").error_type == "format_error"


@pytest.mark.parametrize(
    ("exc", "expected_type"),
    [
        (
            litellm_errors.RateLimitError(
                message="OpenAIException - Rate limit reached", model=_MODEL, llm_provider=_LLM_PROVIDER
            ),
            "rate_limit",
        ),
        (litellm_errors.Timeout(message="Request timed out.", model=_MODEL, llm_provider=_LLM_PROVIDER), "timeout"),
        (Exception("503 Service Unavailable: the request timed out"), "timeout"),
        (Exception("429 too many requests, the service is overloaded"), "rate_limit"),
    ],
    ids=["rate limit", "timeout", "unavailable and timed out", "overloaded and rate limited"],
)
def test_the_families_the_engine_already_knew_keep_their_precedence(exc: Exception, expected_type: str) -> None:
    assert LLMErrorDiagnostic.diagnose(exc, locale="en").error_type == expected_type


_URL = "https://provider.test/v1/chat/completions"


def _response(status: int, *, json: object | None = None, text: str | None = None) -> httpx2.Response:
    """The response an OpenAI SDK exception carries; the SDK builds it with httpx2."""
    return httpx2.Response(status, request=httpx2.Request("POST", _URL), json=json, text=text)


def _rejected_with(body: dict[str, object]) -> openai.BadRequestError:
    return openai.BadRequestError(f"Error code: 400 - {body}", response=_response(400, json=body), body=body)


@pytest.mark.parametrize("locale", _LOCALES)
def test_a_json_body_with_escaped_characters_shows_the_sentence_it_encodes(locale: str) -> None:
    # json.dumps escapes every non-ASCII character as \uXXXX, as several gateways do.
    body = json.dumps({"error": {"message": "参数错误：temperature 超出范围\t请检查", "code": "1210"}})
    exc = litellm_errors.BadRequestError(message=f"OpenAIException - {body}", model=_MODEL, llm_provider=_LLM_PROVIDER)

    shown = LLMErrorDiagnostic.diagnose(exc, locale=locale).user_message

    assert "参数错误：temperature 超出范围 请检查" in shown
    assert "u53c2" not in shown


def test_the_response_payload_is_read_when_the_exception_text_carries_none() -> None:
    exc = litellm_errors.BadRequestError(
        message="OpenAIException - ",
        model=_MODEL,
        llm_provider=_LLM_PROVIDER,
        response=httpx.Response(
            400,
            request=httpx.Request("POST", _URL),
            json={"error": {"message": "参数错误：x", "type": "invalid_request_error"}},
        ),
    )

    assert LLMErrorDiagnostic.diagnose(exc, locale="zh-CN").user_message.endswith("参数错误：x")


def test_the_upstream_error_an_aggregator_wraps_is_what_the_card_shows() -> None:
    upstream = json.dumps({"error": {"message": "Invalid schema for function 'search': 'items' is required"}})
    exc = _rejected_with({"error": {"message": "Provider returned error", "code": 400, "metadata": {"raw": upstream}}})

    shown = LLMErrorDiagnostic.diagnose(exc, locale="en").user_message

    assert shown.endswith("Invalid schema for function 'search': 'items' is required")
    assert "Provider returned error" not in shown


def test_a_plain_text_provider_body_is_still_shown() -> None:
    exc = openai.BadRequestError(
        "field x is invalid", response=_response(400, text="field x is invalid"), body="field x is invalid"
    )

    assert LLMErrorDiagnostic.diagnose(exc, locale="en").user_message.endswith("field x is invalid")


_CLIENT_SIDE_FAILURES: dict[str, Exception] = {
    "provider not provided": litellm_errors.BadRequestError(
        message="LLM Provider NOT provided. Pass in the LLM provider you are trying to call. You passed model=foo",
        model="foo",
        llm_provider="",
    ),
    "unsupported params": litellm_errors.UnsupportedParamsError(
        message="openai does not support parameters: ['foo']. To drop these, set `litellm.drop_params=True`.",
        model=_MODEL,
        llm_provider=_LLM_PROVIDER,
    ),
}
_LIBRARY_SENTENCES = (
    "litellm",
    "llm provider not provided",
    "you passed",
    "drop_params",
    "does not support parameters",
)


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("exc", _CLIENT_SIDE_FAILURES.values(), ids=_CLIENT_SIDE_FAILURES.keys())
def test_a_failure_raised_before_any_request_never_shows_the_library_text(exc: Exception, locale: str) -> None:
    result = LLMErrorDiagnostic.diagnose(exc, locale=locale)
    visible = " ".join([result.user_message, *result.resolution_steps]).lower()

    assert result.error_type == "format_error"
    assert result.user_message
    assert result.resolution_steps
    assert "[missing" not in visible
    assert not any(sentence in visible for sentence in _LIBRARY_SENTENCES)


def test_a_failure_raised_before_any_request_points_at_the_model_settings() -> None:
    result = LLMErrorDiagnostic.diagnose(_CLIENT_SIDE_FAILURES["provider not provided"], locale="zh-CN")

    assert any("设置 > 模型服务" in step for step in result.resolution_steps)


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("exc", _CLIENT_SIDE_FAILURES.values(), ids=_CLIENT_SIDE_FAILURES.keys())
def test_a_failure_raised_before_any_request_names_the_model_the_caller_knows(exc: Exception, locale: str) -> None:
    context = ErrorContext(model_name="acme/chat-large", is_custom_endpoint=False)

    result = LLMErrorDiagnostic.diagnose(exc, context, locale=locale)
    visible = " ".join([result.user_message, *result.resolution_steps]).lower()

    assert result.error_type == "format_error"
    assert "acme/chat-large" in result.user_message
    assert "[missing" not in visible
    assert not any(sentence in visible for sentence in _LIBRARY_SENTENCES)


def test_a_provider_sentence_is_preferred_over_the_model_name() -> None:
    context = ErrorContext(model_name="acme/chat-large", is_custom_endpoint=False)
    exc = _rejected_with({"error": {"message": "Unsupported value: 'temperature'"}})

    message = LLMErrorDiagnostic.diagnose(exc, context, locale="en").user_message

    assert message.endswith("Unsupported value: 'temperature'")
    assert "acme/chat-large" not in message


def test_a_gateway_error_page_is_shown_as_its_visible_text() -> None:
    page = "<html><head><title>Rejected</title></head><body><h1>Invalid request</h1><p>field x</p></body></html>"
    exc = openai.BadRequestError("Error code: 400", response=_response(400, text=page), body=None)

    message = LLMErrorDiagnostic.diagnose(exc, locale="en").user_message

    assert "Invalid request" in message
    assert "<" not in message
