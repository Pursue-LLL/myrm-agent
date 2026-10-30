import json
from collections.abc import Mapping

import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import (
    ErrorKind,
    classify_error,
    classify_failover_reason,
)
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason
from myrm_agent_harness.toolkits.llms.errors.normalize import normalize_provider_error


# Mock exception classes for testing
class APIStatusError(Exception):
    def __init__(self, message: str, status_code: int | None, body: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class APITimeoutError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def test_normalize_provider_error_simple() -> None:
    exc = Exception("Simple error")
    normalized = normalize_provider_error(exc)
    assert normalized.status_code is None
    assert "simple error" in normalized.message


def test_normalize_provider_error_with_status_code() -> None:
    exc = APIStatusError("Not found", 404, {"error": {"message": "Model not found"}})
    normalized = normalize_provider_error(exc)
    assert normalized.status_code == 404
    assert "model not found" in normalized.message


def test_normalize_provider_error_nested_metadata_raw() -> None:
    # Simulate OpenRouter nested error
    inner_error = json.dumps({"error": {"message": "context length exceeded"}})
    body = {"error": {"message": "Upstream error", "metadata": {"raw": inner_error}}}
    exc = APIStatusError("Upstream error", 400, body)
    normalized = normalize_provider_error(exc)
    assert "context length exceeded" in normalized.message
    assert normalized.status_code == 400

    # Ensure it classifies correctly as CONTEXT_OVERFLOW
    assert classify_error(exc) == ErrorKind.CONTEXT_OVERFLOW
    assert classify_failover_reason(exc) == FailoverReason.CONTEXT_OVERFLOW


def test_classify_safety_block() -> None:
    exc = Exception("Request was rejected as a result of the safety system")
    assert classify_error(exc) == ErrorKind.SAFETY_BLOCK
    assert classify_failover_reason(exc) == FailoverReason.SAFETY_BLOCK

    exc2 = Exception("content_policy_violation")
    assert classify_error(exc2) == ErrorKind.SAFETY_BLOCK


@pytest.mark.parametrize(
    "message",
    [
        "litellm.ContentPolicyViolationError: AzureException - The response was filtered",
        'AzureException BadRequestError - {"error": {"message": "filtered", "code": "content_filter"}}',
        "{'error': {'innererror': {'code': 'ResponsibleAIPolicyViolation'}}}",
    ],
    ids=["litellm class name", "content_filter code", "inner policy code"],
)
def test_classify_provider_content_filter_as_safety_block(message: str) -> None:
    assert classify_error(Exception(message)) == ErrorKind.SAFETY_BLOCK


def test_classify_prose_about_a_content_filter_is_not_a_safety_block() -> None:
    assert classify_error(Exception("Unsupported value for the content filter level")) != ErrorKind.SAFETY_BLOCK


# Response shapes the providers document for a guardrail refusal. The refusal is the same for every retry of the same
# request, so it must reach the safety fallback instead of the overload retry ladder an aggregator's 502 would pick.
_GUARDRAIL_REFUSALS = {
    "dashscope input guardrail": (
        400,
        "Error code: 400 - {'error': {'message': 'Input data may contain inappropriate content.', "
        "'type': 'data_inspection_failed', 'code': 'data_inspection_failed'}}",
    ),
    "dashscope output guardrail relayed as 502": (
        502,
        "Upstream error from Alibaba: Output data may contain inappropriate content.",
    ),
    "dashscope output guardrail without status": (
        None,
        "Upstream error from Alibaba: Output data may contain inappropriate content.",
    ),
    "codex cybersecurity flag": (
        None,
        "This content was flagged for possible cybersecurity risk. If this seems wrong, try rephrasing your request.",
    ),
    "minimax output guardrail": (None, "output new_sensitive (1027) [MiniMax-M2.7]"),
    "minimax input guardrail": (400, "Error code: 400 - {'error': {'message': 'Content Exists Risk'}}"),
}


@pytest.mark.parametrize(("status", "message"), _GUARDRAIL_REFUSALS.values(), ids=_GUARDRAIL_REFUSALS.keys())
def test_classify_provider_guardrail_refusal_as_safety_block(status: int | None, message: str) -> None:
    exc = APIStatusError(message, status)

    assert classify_error(exc) == ErrorKind.SAFETY_BLOCK
    assert classify_failover_reason(exc) == FailoverReason.SAFETY_BLOCK


def test_classify_an_unrelated_inspection_error_is_not_a_safety_block() -> None:
    exc = APIStatusError("The data inspection mode is not supported for this model", 400)

    assert classify_error(exc) != ErrorKind.SAFETY_BLOCK


def test_classify_an_identifier_that_only_contains_a_guardrail_code_is_not_a_safety_block() -> None:
    exc = APIStatusError("The new_sensitive_flag parameter is not supported by this model", 400)

    assert classify_error(exc) != ErrorKind.SAFETY_BLOCK


def test_classify_model_not_found() -> None:
    exc = Exception("Model does not exist")
    kind = classify_error(exc)
    assert kind == ErrorKind.MODEL_NOT_FOUND
    assert kind.is_failoverable is True
    assert classify_failover_reason(exc) == FailoverReason.MODEL_NOT_FOUND


def test_classify_openrouter_tool_use_not_supported() -> None:
    exc = Exception("no endpoints found that support tool use")
    kind = classify_error(exc)
    assert kind == ErrorKind.MODEL_NOT_FOUND
    assert kind.is_failoverable is True
    assert classify_failover_reason(exc) == FailoverReason.MODEL_NOT_FOUND
    assert FailoverReason.MODEL_NOT_FOUND.is_failoverable is True


def test_disambiguate_usage_limit() -> None:
    # Transient usage limit -> RATE_LIMIT
    exc1 = Exception("usage limit exceeded. try again in 5 minutes")
    assert classify_error(exc1) == ErrorKind.RATE_LIMIT

    # Hard usage limit -> BILLING
    exc2 = Exception("usage limit exceeded. please upgrade your plan")
    assert classify_error(exc2) == ErrorKind.BILLING


def test_fallback_status_code_probes() -> None:
    # 400 fallback -> FORMAT_ERROR
    exc_400 = APIStatusError("Some weird error", 400, None)
    assert classify_error(exc_400) == ErrorKind.FORMAT_ERROR

    # 413 fallback -> CONTEXT_OVERFLOW
    exc_413 = APIStatusError("Payload", 413, None)
    assert classify_error(exc_413) == ErrorKind.CONTEXT_OVERFLOW

    # 429 fallback -> RATE_LIMIT
    exc_429 = APIStatusError("Slow down", 429, None)
    assert classify_error(exc_429) == ErrorKind.RATE_LIMIT

    # 500 fallback -> OVERLOADED
    exc_500 = APIStatusError("Internal", 500, None)
    assert classify_error(exc_500) == ErrorKind.OVERLOADED


def test_timeout_fallback() -> None:
    exc = APITimeoutError("unexpected eof")
    assert classify_error(exc) == ErrorKind.TIMEOUT


def test_format_error() -> None:
    exc = Exception("schema validation error in arguments")
    assert classify_error(exc) == ErrorKind.RESPONSE_FORMAT_ERROR


def test_empty_error() -> None:
    exc = Exception("")
    assert classify_error(exc) == ErrorKind.UNKNOWN
