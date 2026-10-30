"""Copy contract of the generic `unknown` diagnostic.

The fallback diagnosis reaches end users verbatim (chat error card), so its text must
- carry the provider's message in every shipped locale (a catalog placeholder that the engine never fills
  silently renders an empty tail), and
- still offer next steps (the identifier-free copy of every type is guarded by
  ``test_diagnostic_copy_has_no_identifiers.py``).
"""

import pytest

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic

_LOCALES = ("en", "zh-CN", "ja", "ko", "de")
_RAW_ERROR = "provider rejected the request (code 4711)"


@pytest.mark.parametrize("locale", _LOCALES)
def test_unknown_message_carries_the_provider_text(locale: str) -> None:
    result = LLMErrorDiagnostic.diagnose(RuntimeError(_RAW_ERROR), locale=locale)

    assert result.error_type == "unknown"
    assert result.locale == locale
    assert _RAW_ERROR in result.user_message
    assert not result.user_message.rstrip().endswith((":", "："))


@pytest.mark.parametrize("locale", _LOCALES)
def test_unknown_diagnosis_offers_next_steps(locale: str) -> None:
    result = LLMErrorDiagnostic.diagnose(RuntimeError(_RAW_ERROR), locale=locale)

    assert result.resolution_steps


@pytest.mark.parametrize("locale", _LOCALES)
def test_unknown_message_drops_the_client_library_class_prefix(locale: str) -> None:
    exc = RuntimeError(f"litellm.APIError: litellm.APIError: {_RAW_ERROR}")

    result = LLMErrorDiagnostic.diagnose(exc, locale=locale)

    assert result.error_type == "unknown"
    assert "litellm" not in result.user_message
    assert _RAW_ERROR in result.user_message


def test_unknown_message_is_cut_after_the_prefix_is_dropped() -> None:
    result = LLMErrorDiagnostic.diagnose(RuntimeError("litellm.APIError: " + "x" * 300), locale="en")

    assert "x" * 200 in result.user_message
    assert "x" * 201 not in result.user_message
