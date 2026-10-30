"""Provider failures the shared classifier recognizes read from their own catalogue entries.

An overloaded service, a safety filter, a rejected request and a WAF challenge used to reach the end user as the
client library's raw exception text (``LLM error: litellm.ServiceUnavailableError: ...``, an HTML page for the
challenge). The diagnosis words each of them in every shipped locale, and the families the engine already knew keep
their precedence.
"""

from __future__ import annotations

import pytest
from litellm import exceptions as litellm_errors

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic

_LOCALES = ("en", "zh-CN", "ja", "ko", "de")
_PROVIDER = {"model": "stub-model", "llm_provider": "stub-provider"}
_CLOUDFLARE_PAGE = (
    '<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title></head><body>cf-chl</body></html>'
)

_RECOGNIZED: dict[str, tuple[str, Exception]] = {
    "service unavailable": (
        "overloaded",
        litellm_errors.ServiceUnavailableError(message="AnthropicException - Overloaded", **_PROVIDER),
    ),
    "status 529": ("overloaded", litellm_errors.APIError(status_code=529, message="Overloaded", **_PROVIDER)),
    "safety system": (
        "safety_block",
        litellm_errors.ContentPolicyViolationError(
            message="OpenAIException - Your request was rejected as a result of our safety system. "
            "code: content_policy_violation",
            **_PROVIDER,
        ),
    ),
    "malformed request": (
        "format_error",
        litellm_errors.BadRequestError(
            message="OpenAIException - messages with role 'tool' must be a response to a preceeding message",
            **_PROVIDER,
        ),
    ),
    "waf challenge": (
        "challenge_blocked",
        litellm_errors.APIError(status_code=403, message=_CLOUDFLARE_PAGE, **_PROVIDER),
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


@pytest.mark.parametrize(
    ("exc", "expected_type"),
    [
        (litellm_errors.RateLimitError(message="OpenAIException - Rate limit reached", **_PROVIDER), "rate_limit"),
        (litellm_errors.Timeout(message="Request timed out.", **_PROVIDER), "timeout"),
        (Exception("503 Service Unavailable: the request timed out"), "timeout"),
        (Exception("429 too many requests, the service is overloaded"), "rate_limit"),
    ],
    ids=["rate limit", "timeout", "unavailable and timed out", "overloaded and rate limited"],
)
def test_the_families_the_engine_already_knew_keep_their_precedence(exc: Exception, expected_type: str) -> None:
    assert LLMErrorDiagnostic.diagnose(exc, locale="en").error_type == expected_type
