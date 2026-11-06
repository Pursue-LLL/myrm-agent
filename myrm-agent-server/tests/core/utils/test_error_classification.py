"""
[INPUT] app.core.utils.errors::_classify_exception, internal_error, handle_llm_exception
[OUTPUT] tests of how a failed call is named in the error envelope
[POS] 验证路由兜底（internal_error）与 handle_llm_exception 按 provider 的真实回答给模型调用失败定码，
      且不向用户暴露 provider 原文；数据库 / 网络分类保持不变。
"""

from __future__ import annotations

import json

import httpx
import pytest
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError, LLMHTTPError, LLMResponseError

from app.core.utils.errors import MyrmError, _classify_exception, handle_llm_exception, internal_error
from app.core.utils.errors.constants import (
    _AI_FAILURE_MESSAGES,
    _DEFAULT_LLM_BUSINESS_CODE,
    _FAILOVER_REASON_TO_BUSINESS_CODE,
)
from app.schemas.responses import BusinessCode

_SECRET = "sk-live-0123456789abcdef"


def _provider_failure(status: int) -> LLMHTTPError:
    """What the model transport raises when the provider answers a call with an error status."""
    body = json.dumps({"error": {"message": f"{_SECRET} is not valid for org-acme"}})
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    return LLMHTTPError("openai", status, body, httpx.Response(status, content=body.encode(), request=request))


def _stream_error_event(kind: str) -> LLMAnswerError:
    """An error event inside a stream the provider had accepted (HTTP 200)."""
    return LLMAnswerError("anthropic", {"type": "error", "error": {"type": kind, "message": "event text"}}, stream=True)


@pytest.mark.parametrize(
    ("status", "code", "message"),
    [
        (401, BusinessCode.AI_AUTH_ERROR, "AI service authentication failed"),
        (403, BusinessCode.AI_AUTH_ERROR, "AI service authentication failed"),
        (429, BusinessCode.AI_RATE_LIMIT_ERROR, "AI service rate limited"),
        (402, BusinessCode.AI_RATE_LIMIT_ERROR, "AI service rate limited"),
        (400, BusinessCode.AI_MODEL_ERROR, "AI model call failed"),
        (404, BusinessCode.AI_MODEL_ERROR, "AI model call failed"),
        (503, BusinessCode.AI_MODEL_ERROR, "AI model call failed"),
    ],
)
def test_a_provider_answer_is_named_by_its_status(status: int, code: BusinessCode, message: str) -> None:
    assert _classify_exception(_provider_failure(status)) == (code, message)


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("authentication_error", BusinessCode.AI_AUTH_ERROR),
        ("rate_limit_error", BusinessCode.AI_RATE_LIMIT_ERROR),
        ("overloaded_error", BusinessCode.AI_MODEL_ERROR),
    ],
)
def test_an_error_event_of_an_open_stream_is_named_by_its_kind(kind: str, code: BusinessCode) -> None:
    assert _classify_exception(_stream_error_event(kind))[0] == code


def test_an_answer_that_is_not_the_expected_json_is_a_model_error() -> None:
    failure = LLMResponseError("openai", "openai answered with a non-JSON body: '<html>'")

    assert _classify_exception(failure) == (BusinessCode.AI_MODEL_ERROR, "AI model call failed")


@pytest.mark.parametrize("timeout", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout])
def test_every_httpx_timeout_is_an_ai_timeout(timeout: type[httpx.TimeoutException]) -> None:
    assert _classify_exception(timeout("slow provider")) == (BusinessCode.AI_TIMEOUT_ERROR, "AI service timeout")


@pytest.mark.parametrize(
    "class_name",
    [
        "AuthenticationError",
        "APIKeyError",
        "RateLimitError",
        "Timeout",
        "ReadTimeout",
        "ConnectTimeout",
        "APIError",
        "APIConnectionError",
        "ServiceUnavailableError",
    ],
)
def test_a_class_name_alone_does_not_make_an_error_a_model_failure(class_name: str) -> None:
    """A channel SDK's ``RateLimitError`` or a lock's ``Timeout`` is not a model call."""
    foreign = type(class_name, (Exception,), {})("something unrelated failed")

    assert _classify_exception(foreign) == (BusinessCode.INTERNAL_ERROR, "Internal server error")


@pytest.mark.parametrize(
    ("exception", "code", "message"),
    [
        (
            type("OperationalError", (Exception,), {})("could not connect to server"),
            BusinessCode.DB_CONNECTION_ERROR,
            "Database connection failed",
        ),
        (
            type("InterfaceError", (Exception,), {})("connection closed"),
            BusinessCode.DB_CONNECTION_ERROR,
            "Database connection failed",
        ),
        (
            type("OperationalError", (Exception,), {})("no such column: x"),
            BusinessCode.DB_QUERY_ERROR,
            "Database operation failed",
        ),
        (
            type("DatabaseError", (Exception,), {})("database disk image is malformed"),
            BusinessCode.DB_QUERY_ERROR,
            "Database operation failed",
        ),
        (
            type("IntegrityError", (Exception,), {})("UNIQUE constraint failed"),
            BusinessCode.DB_INTEGRITY_ERROR,
            "Data integrity error",
        ),
        (TimeoutError("busy"), BusinessCode.DB_TIMEOUT_ERROR, "Database operation timeout"),
        (ConnectionRefusedError("refused"), BusinessCode.EXTERNAL_SERVICE_ERROR, "External service connection failed"),
        (OSError("unreachable"), BusinessCode.EXTERNAL_SERVICE_ERROR, "External service connection failed"),
        (ValueError("bad value"), BusinessCode.INTERNAL_ERROR, "Internal server error"),
    ],
)
def test_database_and_network_failures_keep_their_codes(exception: Exception, code: BusinessCode, message: str) -> None:
    assert _classify_exception(exception) == (code, message)


def test_the_catch_all_names_a_failed_model_call_without_the_provider_text() -> None:
    error = internal_error(operation="Compact chat context", exception=_provider_failure(401))

    assert error.status_code == 500
    assert error.detail["code"] == BusinessCode.AI_AUTH_ERROR.value
    assert error.detail["message"] == "Compact chat context failed: AI service authentication failed"
    assert _SECRET not in json.dumps(error.detail)


def test_every_code_a_failure_can_map_to_has_a_user_message() -> None:
    producible = {*_FAILOVER_REASON_TO_BUSINESS_CODE.values(), _DEFAULT_LLM_BUSINESS_CODE, BusinessCode.AI_TIMEOUT_ERROR}

    assert producible <= _AI_FAILURE_MESSAGES.keys()


def test_handle_llm_exception_reports_the_provider_reason() -> None:
    with pytest.raises(MyrmError) as raised:
        handle_llm_exception(_provider_failure(429), "Verification")

    assert raised.value.code == BusinessCode.AI_RATE_LIMIT_ERROR
    assert raised.value.message.startswith("Verification failed: ")
    assert raised.value.message.endswith("[reason: rate_limit_exceeded]")


def test_a_failure_the_classifier_cannot_read_is_a_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreadable(_: Exception) -> None:
        raise RuntimeError("classifier bug")

    monkeypatch.setattr("app.core.utils.errors.base.classify_failover_reason", unreadable)

    with pytest.raises(MyrmError) as raised:
        handle_llm_exception(_provider_failure(401), "Verification")

    assert raised.value.code == BusinessCode.AI_MODEL_ERROR
    assert raised.value.message.endswith("[reason: unknown_error]")
