"""The status, message and codes an LLM exception carries, read into one lower-cased text for the classifier.

A gateway nests the upstream provider's error as a JSON string inside its own (``error.metadata.raw``). That string
comes from outside the process, so the reader may skip it but never fail on it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.errors.normalize import NormalizedError, normalize_provider_error

# Nested far past the interpreter's recursion limit, as a hostile or broken upstream could return it.
_DEEP_OBJECT = '{"a":' * 50_000 + "1" + "}" * 50_000


class _GatewayError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _gateway_error(raw: str, status_code: int = 502) -> _GatewayError:
    body = {"error": {"message": "Provider returned error", "code": status_code, "metadata": {"raw": raw}}}
    return _GatewayError("Provider returned error", status_code, body)


def test_the_upstream_error_a_gateway_wraps_is_part_of_the_message() -> None:
    upstream = json.dumps({"error": {"message": "Context Length Exceeded", "code": "ctx", "type": "Invalid_Request"}})

    normalized = normalize_provider_error(_gateway_error(upstream, 400))

    assert isinstance(normalized, NormalizedError)
    assert normalized.status_code == 400
    assert "context length exceeded" in normalized.message
    assert "ctx" in normalized.message
    assert "invalid_request" in normalized.message


def test_the_status_is_found_down_the_cause_chain() -> None:
    exc = RuntimeError("wrapped")
    exc.__cause__ = _GatewayError("rate limited", 429)

    assert normalize_provider_error(exc).status_code == 429


def test_a_raw_field_nested_beyond_the_recursion_limit_is_skipped() -> None:
    normalized = normalize_provider_error(_gateway_error(_DEEP_OBJECT))

    assert normalized.status_code == 502
    assert "provider returned error" in normalized.message


def test_a_failure_whose_raw_field_is_nested_beyond_the_recursion_limit_is_still_classified() -> None:
    assert classify_error(_gateway_error(_DEEP_OBJECT)) is ErrorKind.OVERLOADED


@pytest.mark.parametrize("raw", ["[1, 2]", "not json", "{", "3", "null"])
def test_a_raw_field_that_is_not_a_json_object_adds_nothing(raw: str) -> None:
    normalized = normalize_provider_error(_gateway_error(raw))

    assert normalized.status_code == 502
    assert normalized.message.startswith("provider returned error | provider returned error")
