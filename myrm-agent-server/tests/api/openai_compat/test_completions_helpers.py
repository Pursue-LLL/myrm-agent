"""Unit tests for the pure request and event helpers of the OpenAI-compatible completions endpoint.

[INPUT] app.api.openai_compat.completions::{_build_chat_history, _extract_query, _extract_system_instruction, _normalize_agent_event, _extract_assistant_text}
[OUTPUT] history/query/system-instruction extraction and agent-event normalization tests
[POS] Pins how an OpenAI messages array becomes the agent's query, history and system instruction, and how the agent's stream events become assistant text.
"""

from __future__ import annotations

import pytest

from app.api.openai_compat.completions import (
    _build_chat_history,
    _extract_assistant_text,
    _extract_query,
    _extract_system_instruction,
    _normalize_agent_event,
)
from app.api.openai_compat.types import ChatCompletionRequest, ChatMessage

TEXT_PART = {"type": "text", "text": "first"}
SECOND_TEXT_PART = {"type": "text", "text": "second"}
IMAGE_PART = {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}


def _request(*messages: tuple[str, str | list[dict[str, object]]]) -> ChatCompletionRequest:
    return ChatCompletionRequest(messages=[ChatMessage(role=role, content=content) for role, content in messages])


def test_history_leaves_out_the_last_message_and_flattens_part_lists() -> None:
    request = _request(("system", "be brief"), ("user", [TEXT_PART]), ("assistant", "hello"), ("user", "now"))

    assert _build_chat_history(request) == [
        ["system", "be brief"],
        ["user", str([TEXT_PART])],
        ["assistant", "hello"],
    ]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("plain question", "plain question"),
        ([TEXT_PART, IMAGE_PART, SECOND_TEXT_PART], "first\nsecond"),
        ([IMAGE_PART], str([IMAGE_PART])),
    ],
    ids=["string", "text-parts-only", "no-text-part"],
)
def test_query_is_the_text_of_the_last_message(content: str | list[dict[str, object]], expected: str) -> None:
    assert _extract_query(_request(("assistant", "earlier"), ("user", content))) == expected


def test_system_instruction_is_the_first_system_message() -> None:
    request = _request(("user", "question"), ("system", "first rule"), ("system", "second rule"))

    assert _extract_system_instruction(request) == "first rule"


def test_system_instruction_flattens_a_part_list() -> None:
    assert _extract_system_instruction(_request(("system", [TEXT_PART]), ("user", "question"))) == str([TEXT_PART])


def test_system_instruction_is_absent_without_a_system_message() -> None:
    assert _extract_system_instruction(_request(("user", "question"))) is None


class _Dumpable:
    def __init__(self, dumped: object) -> None:
        self._dumped = dumped

    def model_dump(self) -> object:
        return self._dumped


class _Dictable:
    def __init__(self, dumped: object) -> None:
        self._dumped = dumped

    def to_dict(self) -> object:
        return self._dumped


def test_a_dict_event_is_returned_as_it_is() -> None:
    event: dict[str, object] = {"type": "message"}

    assert _normalize_agent_event(event) is event


@pytest.mark.parametrize("event", [_Dumpable({"type": "message"}), _Dictable({"type": "message"})], ids=["model_dump", "to_dict"])
def test_an_event_object_is_reduced_to_its_dict(event: object) -> None:
    assert _normalize_agent_event(event) == {"type": "message"}


@pytest.mark.parametrize(
    "event",
    [_Dumpable(["not", "a", "dict"]), _Dictable("not a dict"), object()],
    ids=["model_dump-not-dict", "to_dict-not-dict", "plain-object"],
)
def test_an_event_without_a_dict_form_is_dropped(event: object) -> None:
    assert _normalize_agent_event(event) is None


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"type": "message_chunk", "content": "chunk"}, "chunk"),
        ({"type": "message_chunk", "content": 42}, "42"),
        ({"type": "message_chunk", "content": ""}, ""),
        ({"type": "message_chunk", "content": None}, ""),
        ({"type": "message", "data": "whole answer"}, "whole answer"),
        ({"type": "message", "data": {"content": "from content"}}, "from content"),
        ({"type": "message", "data": {"content": "", "text": "from text"}}, "from text"),
        ({"type": "message", "data": {"content": 5}}, ""),
        ({"type": "message", "data": 7}, ""),
        ({"type": "message_end"}, ""),
        ({}, ""),
    ],
    ids=[
        "chunk-text",
        "chunk-number",
        "chunk-empty",
        "chunk-none",
        "message-string",
        "message-content",
        "message-text-after-empty-content",
        "message-non-string-content",
        "message-non-dict-data",
        "other-event",
        "no-type",
    ],
)
def test_assistant_text_comes_only_from_message_events(event: dict[str, object], expected: str) -> None:
    assert _extract_assistant_text(event) == expected
