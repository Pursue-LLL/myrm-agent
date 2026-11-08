"""Overflow answers that carry no error code of their own: the sentence alone must send the request to compaction.

The bodies are what each provider answers with a 400 (422 for TGI). A request whose history outgrew the model's window
is only repaired when it is recognised as one; read as a plain rejected request it ends the run instead.
"""

from __future__ import annotations

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import (
    ErrorKind,
    classify_error,
    classify_failover_reason,
    is_context_overflow,
    is_payload_overflow,
)
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError

_GEMINI = {
    "error": {
        "code": 400,
        "message": "The input token count (1100000) exceeds the maximum number of tokens allowed (1048576).",
        "status": "INVALID_ARGUMENT",
    }
}


def _answer(status: int, body: object) -> LLMHTTPError:
    request = httpx.Request("POST", "https://provider.test/v1/chat")
    response = httpx.Response(status, json=body, request=request)
    return LLMHTTPError("openai", status, response.text, response)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, _GEMINI),
        # Gemini's OpenAI-compatible endpoint wraps the same error object in a list.
        (400, [_GEMINI]),
        (400, {"message": "Current length is 20000 while limit is 8192", "type": "invalid_request_error"}),
        (
            422,
            {
                "error": "Input validation error: `inputs` tokens + `max_new_tokens` must be <= 8193. "
                "Given: 9000 `inputs` tokens and 100 `max_new_tokens`",
                "error_type": "validation",
            },
        ),
        (
            400,
            {"error": {"message": "The input (9000 tokens) is longer than the model's context length (8192 tokens)."}},
        ),
        (400, {"error": {"message": "Maximum input length is 32768 tokens, but got 40000 tokens."}}),
        (400, {"error": {"message": "The model's maximum context limit is 8192 tokens, you sent 9000."}}),
        (
            400,
            {
                "message": "too many tokens: total number of tokens in the prompt cannot exceed 4081 - received 4885. "
                "Try using a shorter prompt, or enabling prompt truncation."
            },
        ),
    ],
    ids=[
        "gemini",
        "gemini-list",
        "cerebras",
        "tgi",
        "longer-than-context",
        "max-input-length",
        "context-limit",
        "cohere",
    ],
)
def test_a_wording_without_an_error_code_is_a_context_overflow(status: int, body: object) -> None:
    error = _answer(status, body)

    assert classify_failover_reason(error) == FailoverReason.CONTEXT_OVERFLOW
    assert classify_error(error) == ErrorKind.CONTEXT_OVERFLOW
    assert is_context_overflow(error) is True
    # Shrinking the history repairs it; dropping images would not.
    assert is_payload_overflow(error) is False


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"error": {"message": "Maximum input length is 256 characters."}}),
        (400, {"message": "Current length is 5"}),
        (400, {"message": "while limit is not set"}),
        (
            400,
            {
                "error": {
                    "message": "Invalid 'user': string too long. Expected a string with maximum length 64, "
                    "but got a string with length 100 instead.",
                    "code": "string_above_max_length",
                }
            },
        ),
        (429, {"message": "Too many tokens, please wait before trying again."}),
    ],
    ids=["length-in-characters", "half-of-cerebras", "other-half-of-cerebras", "rejected-user-parameter", "throttle"],
)
def test_a_similar_sentence_that_is_not_an_overflow_is_not_one(status: int, body: object) -> None:
    assert is_context_overflow(_answer(status, body)) is False
