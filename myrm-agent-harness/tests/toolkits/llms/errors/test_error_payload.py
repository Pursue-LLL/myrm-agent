"""What the provider itself said, read from an LLM exception.

SDKs and gateways put the provider's payload in different places: the OpenAI and Anthropic SDKs keep the parsed
``body`` on the exception, litellm keeps the ``httpx`` response and re-raises the SDK's exception from inside its
own, and an aggregator wraps the upstream error one level deeper. A failure the client library raises before any
request is sent has no payload at all, and its words are the library's, not the provider's.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType

import httpx
import httpx2
import openai
import pytest
from litellm import exceptions as litellm_errors

from myrm_agent_harness.toolkits.llms.errors.error_payload import (
    MAX_CHAIN_DEPTH,
    extract_error_body,
    is_json_shaped,
    parse_json_object,
    provider_error_message,
    walk_exception_chain,
)

_MODEL = "stub-model"
_PROVIDER = "stub-provider"


_URL = "https://provider.test/v1/chat/completions"
# Nested far past the interpreter's recursion limit, as a hostile or broken upstream could return it.
_DEEP_OBJECT = '{"a":' * 50_000 + "1" + "}" * 50_000


def _openai_response(status: int, *, json: object | None = None, text: str | None = None) -> httpx2.Response:
    """The response an OpenAI SDK exception carries; the SDK builds it with httpx2."""
    return httpx2.Response(status, request=httpx2.Request("POST", _URL), json=json, text=text)


def _response(
    status: int, *, json: object | None = None, text: str | None = None, content: bytes | None = None
) -> httpx.Response:
    """The response a litellm exception carries."""
    return httpx.Response(status, request=httpx.Request("POST", _URL), json=json, text=text, content=content)


def _openai_rejection(body: Mapping[str, object] | str) -> openai.BadRequestError:
    response = _openai_response(400, json=body) if isinstance(body, Mapping) else _openai_response(400, text=body)
    return openai.BadRequestError(f"Error code: 400 - {body}", response=response, body=body)


def _litellm_rejection(response: httpx.Response | None = None, message: str = "") -> litellm_errors.BadRequestError:
    return litellm_errors.BadRequestError(message=message, model=_MODEL, llm_provider=_PROVIDER, response=response)


def _raised_from(cause: Exception) -> Exception:
    """litellm's own exception raised inside the handler of the SDK's, as litellm does it."""
    try:
        try:
            raise cause
        except Exception as inner:
            raise _litellm_rejection(message="OpenAIException - ") from inner
    except Exception as wrapped:
        return wrapped


_OPENAI_BODY = {"error": {"message": "Invalid value: 'foo'.", "type": "invalid_request_error"}}
_ANTHROPIC_BODY = {
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "tool_use ids must be unique"},
}


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_openai_rejection(_OPENAI_BODY), "Invalid value: 'foo'."),
        (_openai_rejection(_ANTHROPIC_BODY), "tool_use ids must be unique"),
        (_openai_rejection({"message": "top-level sentence"}), "top-level sentence"),
        (_openai_rejection({"detail": "gateway detail"}), "gateway detail"),
        (_openai_rejection({"error": "bare error string"}), "bare error string"),
        (_openai_rejection("field x is invalid"), "field x is invalid"),
    ],
    ids=["openai", "anthropic", "top-level message", "detail", "error string", "plain text body"],
)
def test_the_sdk_body_gives_the_providers_sentence(exc: Exception, expected: str) -> None:
    assert provider_error_message(exc) == expected


def test_litellm_keeps_the_payload_on_the_http_response_not_on_the_exception() -> None:
    exc = _litellm_rejection(_response(400, json=_OPENAI_BODY))

    assert getattr(exc, "body", None) is None
    assert provider_error_message(exc) == "Invalid value: 'foo'."


def test_the_payload_is_found_down_the_cause_chain() -> None:
    assert provider_error_message(_raised_from(_openai_rejection(_OPENAI_BODY))) == "Invalid value: 'foo'."


def test_a_json_payload_with_escaped_characters_is_decoded_by_the_json_parser() -> None:
    body = json.dumps({"error": {"message": "参数错误：temperature 超出范围\t请检查"}})

    assert provider_error_message(_litellm_rejection(_response(400, content=body.encode()))) == (
        "参数错误：temperature 超出范围\t请检查"
    )


def test_the_upstream_error_an_aggregator_wraps_beats_the_wrapper_sentence() -> None:
    upstream = json.dumps({"error": {"message": "Invalid schema for function 'search': 'items' is required"}})
    body = {
        "error": {
            "message": "Provider returned error",
            "code": 400,
            "metadata": {"raw": upstream, "provider_name": "Azure"},
        }
    }

    assert (
        provider_error_message(_openai_rejection(body)) == "Invalid schema for function 'search': 'items' is required"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Upstream said no", "Upstream said no"),
        ({"error": {"message": "nested mapping"}}, "nested mapping"),
        ("", "Provider returned error"),
        ("{not json", "Provider returned error"),
        ("[400] Upstream said no", "[400] Upstream said no"),
    ],
    ids=["plain text", "mapping", "empty", "broken json", "bracketed number"],
)
def test_an_aggregators_raw_field_may_be_text_a_mapping_or_missing(raw: object, expected: str) -> None:
    body = {"error": {"message": "Provider returned error", "metadata": {"raw": raw}}}

    assert provider_error_message(_openai_rejection(body)) == expected


@pytest.mark.parametrize(
    "exc",
    [
        litellm_errors.BadRequestError(
            message="LLM Provider NOT provided. Pass in the LLM provider you are trying to call. You passed model=foo",
            model="foo",
            llm_provider="",
        ),
        litellm_errors.UnsupportedParamsError(
            message="openai does not support parameters: ['foo']", model=_MODEL, llm_provider=_PROVIDER
        ),
        _litellm_rejection(_response(400, content=b"")),
        ValueError("temperature must be between 0 and 1"),
        _openai_rejection({}),
    ],
    ids=["provider not provided", "unsupported params", "empty response", "plain exception", "empty body"],
)
def test_a_failure_with_no_provider_payload_has_no_provider_sentence(exc: Exception) -> None:
    assert provider_error_message(exc) is None


def test_a_self_referencing_cause_does_not_loop() -> None:
    exc = ValueError("loop")
    exc.__cause__ = exc

    assert walk_exception_chain(exc) == [exc]
    assert provider_error_message(exc) is None


def test_the_chain_walk_is_bounded() -> None:
    exc: BaseException = ValueError("root")
    for depth in range(MAX_CHAIN_DEPTH * 2):
        outer = ValueError(f"level {depth}")
        outer.__cause__ = exc
        exc = outer

    assert len(walk_exception_chain(exc)) == MAX_CHAIN_DEPTH


def test_the_body_attribute_wins_over_the_response_and_a_mapping_is_copied_to_a_dict() -> None:
    exc = _openai_rejection(_OPENAI_BODY)
    exc.body = MappingProxyType({"error": {"message": "from the attribute"}})

    body = extract_error_body(exc)

    assert type(body) is dict
    assert body == {"error": {"message": "from the attribute"}}


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("no payload"),
        _litellm_rejection(_response(400, text="plain")),
        _litellm_rejection(_response(400, json=[1])),
    ],
    ids=["no payload", "text response", "non-object json"],
)
def test_a_missing_or_non_object_body_is_an_empty_dict(exc: Exception) -> None:
    assert extract_error_body(exc) == {}


@pytest.mark.parametrize(
    ("text", "expected"),
    [('{"a": 1}', {"a": 1}), ("{}", {}), ("[1]", None), ("3", None), ("null", None), ("{", None), ("", None)],
    ids=["object", "empty object", "array", "number", "null", "truncated", "empty"],
)
def test_only_a_json_object_is_parsed(text: str, expected: dict[str, object] | None) -> None:
    assert parse_json_object(text) == expected


def test_a_json_object_nested_beyond_the_recursion_limit_is_not_parsed() -> None:
    assert parse_json_object(_DEEP_OBJECT) is None


def test_an_aggregators_raw_field_nested_beyond_the_recursion_limit_leaves_the_wrapper_sentence() -> None:
    body = {"error": {"message": "Provider returned error", "metadata": {"raw": _DEEP_OBJECT}}}

    assert provider_error_message(_openai_rejection(body)) == "Provider returned error"


# An array is data when it opens with an object, an array or a string, or closes at once. A bracketed number, date or
# word in front of text is a tag the provider or a gateway put there, so the text after it is still words.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{}", True),
        ('  {"a": 1}', True),
        ("[]", True),
        ("[ ]", True),
        ('["a"]', True),
        ("[{'a': 1}]", True),
        ("[['a']]", True),
        ('[{"error": {"message": "x"}', True),
        ("Bad Request", False),
        ("", False),
        ("an {inline} brace", False),
        ("[Errno 28] No space left on device", False),
        ("[ERROR] upstream down", False),
        ("[400] Bad Request: voice id invalid", False),
        ("[400 Bad Request] during [POST]", False),
        ("[1004] speaker id is not allowed", False),
        ("[2024-10-30 12:00:00] upstream timeout", False),
        ("[-1] unknown", False),
        ("[1, 2]", False),
    ],
    ids=[
        "object",
        "indented object",
        "empty array",
        "empty array with a space",
        "string array",
        "python repr array",
        "nested array",
        "truncated array of objects",
        "sentence",
        "empty",
        "brace inside a sentence",
        "errno tag",
        "level tag",
        "status code tag",
        "status line tag",
        "provider code tag",
        "timestamp tag",
        "negative code tag",
        "number array",
    ],
)
def test_text_is_json_shaped_when_it_opens_as_an_object_or_an_array(text: str, expected: bool) -> None:
    assert is_json_shaped(text) is expected


@pytest.mark.parametrize(
    "text",
    ["[ERROR] upstream down", "[400] Bad Request: voice id invalid", "[2024-10-30 12:00:00] upstream timeout"],
    ids=["level tag", "status code tag", "timestamp tag"],
)
def test_a_plain_text_body_that_opens_with_a_tag_is_still_the_providers_sentence(text: str) -> None:
    assert provider_error_message(_openai_rejection(text)) == text
