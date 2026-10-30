"""A provider payload that carries no sentence is data, so no card prints it.

A rejected request and an unrecognized failure quote the provider's words. When the body holds none (an empty object,
a status and code pair, a list of validation records) the exception text is only the SDK's rendering of that data, and
quoting it shows the user ``{'code': 1027, 'msg': ...}`` instead of anything they can act on.
"""

from __future__ import annotations

import httpx2
import openai
import pytest
from litellm import exceptions as litellm_errors

from myrm_agent_harness.agent.errors.diagnostics import ErrorContext, LLMErrorDiagnostic

_MODEL = "stub-model"
_BASE_URL = "https://provider.test/v1"
_CONTEXT = ErrorContext(model_name=_MODEL, is_custom_endpoint=False, base_url=_BASE_URL)
_DATA_MARKERS = ("{", "}", "[", "]", "'code'", "'msg'", "'detail'")

_WITHOUT_SENTENCE: dict[str, object] = {
    "empty object": {},
    "empty array": [],
    "code and msg": {"code": 1027, "msg": "output sensitive"},
    "base_resp": {"base_resp": {"status_code": 1027, "status_msg": "sensitive"}},
    "error_code and error_msg": {"error_code": 17, "error_msg": "Open api daily request limit reached"},
    "error object with a code only": {"error": {"code": 400}},
    "validation records": {"detail": [{"loc": ["body", "x"], "msg": "field required", "type": "missing"}]},
}


def _rejection(status: int, body: object) -> openai.APIStatusError:
    """The exception the OpenAI SDK raises for a response, built the way the SDK builds it."""
    request = httpx2.Request("POST", f"{_BASE_URL}/chat/completions")
    response = (
        httpx2.Response(status, request=request, text=body)
        if isinstance(body, str)
        else httpx2.Response(status, request=request, json=body)
    )
    return openai.OpenAI(api_key="stub-key", base_url=_BASE_URL)._make_status_error_from_response(response)


@pytest.mark.parametrize("body", _WITHOUT_SENTENCE.values(), ids=_WITHOUT_SENTENCE.keys())
def test_a_rejected_request_whose_body_has_no_sentence_names_the_model(body: object) -> None:
    result = LLMErrorDiagnostic.diagnose(_rejection(400, body), _CONTEXT, locale="en")

    assert result.error_type == "format_error"
    assert _MODEL in result.user_message
    assert not any(marker in result.user_message for marker in _DATA_MARKERS)


@pytest.mark.parametrize("body", _WITHOUT_SENTENCE.values(), ids=_WITHOUT_SENTENCE.keys())
def test_a_rejected_request_whose_body_has_no_sentence_and_no_known_model_states_the_failure_plainly(
    body: object,
) -> None:
    result = LLMErrorDiagnostic.diagnose(_rejection(400, body), None, locale="en")

    assert result.error_type == "format_error"
    assert not any(marker in result.user_message for marker in _DATA_MARKERS)


@pytest.mark.parametrize("body", _WITHOUT_SENTENCE.values(), ids=_WITHOUT_SENTENCE.keys())
def test_an_unrecognized_failure_whose_body_has_no_sentence_names_the_exception(body: object) -> None:
    exc = _rejection(422, body)

    result = LLMErrorDiagnostic.diagnose(exc, _CONTEXT, locale="en")

    assert result.error_type == "unknown"
    assert type(exc).__name__ in result.user_message
    assert not any(marker in result.user_message for marker in _DATA_MARKERS)


@pytest.mark.parametrize(
    ("body", "shown"),
    [
        ("Bad Request", "Bad Request"),
        ({"errors": [{"message": "Field x is required"}]}, "Field x is required"),
        ({"error": {"message": "Invalid value: 'foo'"}}, "Invalid value: 'foo'"),
    ],
    ids=["plain text", "errors list", "error message"],
)
def test_a_body_that_carries_a_sentence_still_shows_it(body: object, shown: str) -> None:
    result = LLMErrorDiagnostic.diagnose(_rejection(400, body), _CONTEXT, locale="en")

    assert result.error_type == "format_error"
    assert shown in result.user_message


_TAGGED_WORDS = {
    "errno tag": "[Errno 28] No space left on device",
    "level tag": "[ERROR] upstream down",
    "status code tag": "[400] Bad Request: voice id invalid",
    "provider code tag": "[1004] speaker id is not allowed",
    "timestamp tag": "[2024-10-30 12:00:00] voice id invalid",
}


@pytest.mark.parametrize("text", _TAGGED_WORDS.values(), ids=_TAGGED_WORDS.keys())
def test_failure_text_that_opens_with_a_bracketed_tag_is_still_shown(text: str) -> None:
    result = LLMErrorDiagnostic.diagnose(RuntimeError(text), _CONTEXT, locale="en")

    assert result.error_type == "unknown"
    assert text in result.user_message


@pytest.mark.parametrize("words", _TAGGED_WORDS.values(), ids=_TAGGED_WORDS.keys())
def test_a_rejection_whose_words_after_the_provider_framing_open_with_a_tag_shows_them(words: str) -> None:
    exc = litellm_errors.BadRequestError(
        message=f"VolcengineException - {words}", model=_MODEL, llm_provider="volcengine"
    )

    result = LLMErrorDiagnostic.diagnose(exc, _CONTEXT, locale="en")

    assert result.error_type == "format_error"
    assert words in result.user_message


def test_a_body_whose_message_is_empty_still_names_the_model() -> None:
    result = LLMErrorDiagnostic.diagnose(_rejection(400, {"message": ""}), _CONTEXT, locale="en")

    assert result.error_type == "format_error"
    assert _MODEL in result.user_message
