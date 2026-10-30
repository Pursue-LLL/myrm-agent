"""Provider failures the shared classifier recognizes read from their own catalogue entries.

An overloaded service, a safety filter, a rejected request and a WAF challenge used to reach the end user as the
client library's raw exception text (``LLM error: litellm.ServiceUnavailableError: ...``, an HTML page for the
challenge). The diagnosis words each of them in every shipped locale, and the families the engine already knew keep
their precedence. A rejected request also tells what the provider objected to, so a mistyped model name or an invalid
parameter can be fixed from the card.
"""

from __future__ import annotations

import pytest
from litellm import exceptions as litellm_errors

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic

_LOCALES = ("en", "zh-CN", "ja", "ko", "de")
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
