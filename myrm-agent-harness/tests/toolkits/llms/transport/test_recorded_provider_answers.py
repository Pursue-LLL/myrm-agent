"""Provider answers recorded from a live multi-protocol gateway, replayed through the whole call path.

The golden suite pins what a request looks like; this one pins what an answer turns into. Each fixture in
``recorded/`` is the byte-exact body a provider endpoint returned for a request the adapter built itself (a tool
call for two cities in one turn, and a one-word answer), kept as lines. ``expect`` was extracted from those lines by
an independent reader of each protocol, so the test compares the production decoders with a second implementation
on real bytes: text, reasoning, tool calls (id, name, arguments) and the token usage that is billed.

The gateway translates between protocols, so these are the bodies it renders for each protocol, not the bytes of
the vendor's own service.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Final

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.tools import tool

from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model
from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker, init_token_tracker, reset_token_tracker

_RECORDED: Final = Path(__file__).parent / "recorded"
_PROVIDER: Final = {
    "chat": "openai",
    "responses": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "ollama": "ollama",
}
_ROOT: Final = {"chat": "/v1", "responses": "/v1", "anthropic": "", "gemini": "/v1beta", "ollama": ""}
_MINTED_ID: Final = re.compile(r"call_[0-9a-f]{24}(__thought__.+)?")

Fixture = dict[str, object]


@tool
def get_weather(city: str) -> str:
    """Get the current temperature in a city, in degrees Celsius."""
    return f"{city}: 21"


def _cases() -> list[tuple[Fixture, str]]:
    cases: list[tuple[Fixture, str]] = []
    for path in sorted(_RECORDED.glob("*.json")):
        fixture: Fixture = json.loads(path.read_text(encoding="utf-8"))
        scenarios = fixture["scenarios"]
        assert isinstance(scenarios, dict)
        cases.extend((fixture, name) for name in scenarios)
    return cases


_CASES: Final = _cases()
_IDS: Final = [f"{fixture['config']}-{name}" for fixture, name in _CASES]


@pytest.fixture
def tracker() -> Iterator[TokenTracker]:
    yield init_token_tracker()
    reset_token_tracker()


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, object]], list[httpx.Request]]:
    """Answer every provider request with one recorded body; ``serve(record)`` returns the requests seen."""
    seen: list[httpx.Request] = []

    def arm(record: dict[str, object]) -> list[httpx.Request]:
        body = "\n".join(record["lines"]).encode()  # type: ignore[arg-type]
        headers = {"content-type": str(record["content_type"])}

        def respond(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, headers=headers, content=body)

        monkeypatch.setattr(
            http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond))
        )
        monkeypatch.setattr(http, "_sync_client", lambda proxy: httpx.Client(transport=httpx.MockTransport(respond)))
        return seen

    return arm


def _model(fixture: Fixture, *, streaming: bool) -> object:
    wire = str(fixture["wire"])
    extra = {"wire_protocol": "responses"} if wire == "responses" else {}
    return create_chat_model(
        model=f"{_PROVIDER[wire]}/{fixture['model']}",
        base_url="http://provider.test" + _ROOT[wire],
        api_key="test-key",
        temperature=0.0,
        streaming=streaming,
        **extra,
    )


def _text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict))


def _assert_matches(fixture: Fixture, record: dict[str, object], message: AIMessage, tracker: TokenTracker) -> None:
    expect = record["expect"]
    assert isinstance(expect, dict)
    assert _text(message) == expect["text"]
    assert message.additional_kwargs.get("reasoning_content", "") == expect["reasoning"]
    assert message.invalid_tool_calls == []

    expected_calls = expect["tool_calls"]
    assert [(c["name"], c["args"]) for c in message.tool_calls] == [(c["name"], c["args"]) for c in expected_calls]
    ids = [c["id"] for c in message.tool_calls]
    assert len(set(ids)) == len(ids), "every call needs its own id"
    for call, expected in zip(message.tool_calls, expected_calls, strict=True):
        if expected["id"] is None:
            assert _MINTED_ID.fullmatch(call["id"]), f"{fixture['wire']} has no call ids of its own: {call['id']!r}"
        else:
            assert call["id"] == expected["id"], "the provider's call id must survive, it is what the result answers"

    prompt, completion, cached = expect["usage"]
    assert tracker.call_count == 1
    assert (tracker.usage.prompt_tokens, tracker.usage.completion_tokens, tracker.usage.cached_tokens) == (
        prompt,
        completion,
        cached,
    )


def _prompt_and_runnable(model: object, record: dict[str, object], scenario: str) -> tuple[list[HumanMessage], object]:
    runnable = model.bind_tools([get_weather]) if scenario.startswith("tools2") else model  # type: ignore[attr-defined]
    return [HumanMessage(content=str(record["prompt"]))], runnable


@pytest.mark.parametrize(("fixture", "scenario"), _CASES, ids=_IDS)
async def test_an_async_call_turns_the_recorded_answer_into_the_right_message(
    fixture: Fixture,
    scenario: str,
    serve: Callable[[dict[str, object]], list[httpx.Request]],
    tracker: TokenTracker,
) -> None:
    record = fixture["scenarios"][scenario]  # type: ignore[index]
    seen = serve(record)
    prompt, runnable = _prompt_and_runnable(_model(fixture, streaming=scenario.endswith("_stream")), record, scenario)

    if scenario.endswith("_stream"):
        message: AIMessage | None = None
        async for part in runnable.astream(prompt):  # type: ignore[attr-defined]
            message = part if message is None else message + part  # type: ignore[assignment]
    else:
        message = await runnable.ainvoke(prompt)  # type: ignore[attr-defined]

    assert message is not None
    assert [r.url.path for r in seen] == [record["path"]]
    _assert_matches(fixture, record, message, tracker)


@pytest.mark.parametrize(("fixture", "scenario"), _CASES, ids=_IDS)
def test_a_sync_call_gets_the_same_message(
    fixture: Fixture,
    scenario: str,
    serve: Callable[[dict[str, object]], list[httpx.Request]],
    tracker: TokenTracker,
) -> None:
    record = fixture["scenarios"][scenario]  # type: ignore[index]
    serve(record)
    prompt, runnable = _prompt_and_runnable(_model(fixture, streaming=scenario.endswith("_stream")), record, scenario)

    if scenario.endswith("_stream"):
        message: AIMessageChunk | None = None
        for part in runnable.stream(prompt):  # type: ignore[attr-defined]
            message = part if message is None else message + part
    else:
        message = runnable.invoke(prompt)  # type: ignore[attr-defined]

    assert message is not None
    _assert_matches(fixture, record, message, tracker)
