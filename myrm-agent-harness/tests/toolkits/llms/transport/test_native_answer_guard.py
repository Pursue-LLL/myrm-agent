"""A 200 answer that parses as JSON but is no answer of the wire: another API's reply, a status object.

Read as an empty answer it would report a dead or wrong endpoint as healthy (the connection test of a mistyped Ollama
address answered "OK"), so it fails like the OpenAI wire's answer without a choice: as a provider fault the caller
repeats. A body that is an answer, however empty, stays one.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_response,
    bedrock_response,
    gemini_generate,
    ollama_chat,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError
from myrm_agent_harness.toolkits.llms.transport.profile import Route, resolve_route

Payload = dict[str, object]
Parse = Callable[[Route, Payload], Payload]

_ANTHROPIC = (anthropic_response.parse, resolve_route("anthropic/claude-sonnet-4-5", api_key="k"), "a message")
_GEMINI = (gemini_generate.parse, resolve_route("gemini/gemini-2.5-pro", api_key="k"), "a candidate")
_OLLAMA = (ollama_chat.parse, resolve_route("ollama/llama3.1", api_base="http://localhost:11434"), "a message")
_BEDROCK = (
    bedrock_response.parse,
    resolve_route("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", api_key="k"),
    "a message",
)
_WIRES = [_ANTHROPIC, _GEMINI, _OLLAMA, _BEDROCK]
_WIRE_IDS = ["anthropic", "gemini", "ollama", "bedrock"]

# What a server of another API, or a status endpoint, answers to a chat request with HTTP 200.
_OPENAI_COMPLETION: Payload = {
    "id": "c1",
    "object": "chat.completion",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
}


@pytest.mark.parametrize(("parse", "route", "what"), _WIRES, ids=_WIRE_IDS)
@pytest.mark.parametrize(
    "body",
    [{}, {"foo": "bar"}, {"status": "ok"}, _OPENAI_COMPLETION],
    ids=["empty-object", "foreign-object", "status-object", "openai-completion"],
)
def test_a_json_object_that_is_not_the_wires_answer_is_the_providers_fault_and_repeated(
    parse: Parse, route: Route, what: str, body: Payload
) -> None:
    with pytest.raises(LLMResponseError) as caught:
        parse(route, dict(body))

    assert caught.value.status_code == 502
    assert str(caught.value).startswith(f"{route.profile.id} answered without {what}: ")
    assert classify_error(caught.value) == ErrorKind.OVERLOADED


def test_the_failure_shows_the_start_of_what_answered() -> None:
    parse, route, _ = _OLLAMA

    with pytest.raises(LLMResponseError, match=r'\{"foo": "bar"\}'):
        parse(route, {"foo": "bar"})


@pytest.mark.parametrize(
    ("parse", "route", "body"),
    [
        (
            _ANTHROPIC[0],
            _ANTHROPIC[1],
            {"type": "message", "role": "assistant", "content": [], "stop_reason": "end_turn"},
        ),
        (_GEMINI[0], _GEMINI[1], {"candidates": []}),
        (_GEMINI[0], _GEMINI[1], {"promptFeedback": {"blockReason": "SAFETY"}}),
        (_OLLAMA[0], _OLLAMA[1], {"model": "m", "message": {"role": "assistant", "content": ""}, "done": True}),
        (_BEDROCK[0], _BEDROCK[1], {"output": {"message": {"role": "assistant", "content": []}}}),
    ],
    ids=[
        "anthropic-empty-content",
        "gemini-no-candidates",
        "gemini-blocked-prompt",
        "ollama-empty-text",
        "bedrock-empty",
    ],
)
def test_an_answer_that_says_nothing_is_still_an_answer(parse: Parse, route: Route, body: Payload) -> None:
    choice = parse(route, body)["choices"][0]  # type: ignore[index]

    assert choice["message"]["content"] is None
