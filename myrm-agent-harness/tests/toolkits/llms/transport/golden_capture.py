"""Records the outbound HTTP requests of the real model factory and adapter for a fixed scenario matrix.

[INPUT]
- core.llm::create_chat_model (POS: the production model factory)
- httpx (POS: patched ``send`` that records the request and answers with a canned, valid provider response)

[OUTPUT]
- capture_all: {"provider|base|scenario": {"requests": [...], "error": str}} for every provider x scenario

[POS]
Library-agnostic request capture. The committed baseline ``golden_baseline.json`` was recorded the same way at
commit b6959e7d7e, when the factory still called the previous multi-provider client library (litellm 1.97.0) with
the production configuration applied; the golden test replays the matrix on the current transport and diffs the
two. Only the final request on the wire is observed, so the comparison does not depend on any library internals.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx
import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model

Record = dict[str, object]
Case = dict[str, object]

_SECRET_HEADERS = frozenset({"authorization", "x-api-key", "api-key", "x-goog-api-key"})
_KEPT_HEADER_PREFIXES = ("anthropic-", "x-", "api-", "openai-", "http-referer", "authorization", "content-type")
_IGNORED_HEADERS = frozenset({"content-type"})

_CHAT_JSON = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1,
    "model": "m",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
}
_CHAT_SSE = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m","choices":[{"index":0,"delta":{"role":"assistant","content":"ok"},"finish_reason":null}]}\n\n'
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1,"total_tokens":4}}\n\n'
    "data: [DONE]\n\n"
)
_ANTHROPIC_JSON = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "m",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 3, "output_tokens": 1},
}
_ANTHROPIC_SSE = (
    'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","model":"m","content":[],"stop_reason":null,"usage":{"input_tokens":3,"output_tokens":1}}}\n\n'
    'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}\n\n'
    'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
    'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}\n\n'
    'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)
_GEMINI_JSON = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP", "index": 0}],
    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1, "totalTokenCount": 4},
}
_OLLAMA_CHAT_NDJSON = (
    '{"model":"m","created_at":"2024-01-01T00:00:00Z","message":{"role":"assistant","content":"ok"},'
    '"done":true,"prompt_eval_count":3,"eval_count":1}\n'
)
_RESPONSES_JSON = {
    "id": "resp_1",
    "object": "response",
    "created_at": 1,
    "status": "completed",
    "model": "m",
    "output": [
        {
            "type": "message",
            "id": "msg_1",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "ok", "annotations": []}],
        }
    ],
    "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
}
_RESPONSES_SSE = (
    "event: response.output_text.delta\ndata: "
    + json.dumps(
        {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "ok"}
    )
    + "\n\n"
    "event: response.completed\ndata: "
    + json.dumps({"type": "response.completed", "response": _RESPONSES_JSON})
    + "\n\n"
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    }
]
_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "r",
        "schema": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
    },
}
_BASE_URL = "http://golden.invalid/v1"

# provider key -> (model id as the settings layer builds it, extra factory kwargs)
PROVIDERS: dict[str, tuple[str, dict[str, object]]] = {
    "openai": ("openai/gpt-4o-mini", {}),
    "openai_gpt5": ("openai/gpt-5", {}),
    "openai_o3": ("openai/o3", {}),
    "anthropic": ("anthropic/claude-sonnet-4-5", {}),
    "gemini": ("gemini/gemini-2.5-flash", {}),
    "deepseek": ("deepseek/deepseek-chat", {}),
    "deepseek_reasoner": ("deepseek/deepseek-reasoner", {}),
    "openrouter": ("openrouter/anthropic/claude-sonnet-4.5", {}),
    "zai": ("zai/glm-4.6", {}),
    "xai": ("xai/grok-4", {}),
    "ollama": ("ollama/llama3.1", {}),
    "moonshot": ("moonshot/kimi-k2-0905-preview", {}),
    "lm_studio": ("lm_studio/qwen2.5", {}),
    "mistral": ("mistral/mistral-large-latest", {}),
    "together_ai": ("together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", {}),
    "volcengine": ("volcengine/doubao-seed-1-6", {}),
    "fireworks_ai": ("fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct", {}),
    "minimax": ("minimax/MiniMax-M2", {}),
    "groq": ("groq/llama-3.3-70b-versatile", {}),
    "dashscope": ("dashscope/qwen-plus", {}),
    "azure": ("azure/gpt-4o", {"model_kwargs": {"api_version": "2024-10-21"}}),
    "perplexity": ("perplexity/sonar", {}),
    "cohere_chat": ("cohere_chat/command-r-plus", {}),
    "bedrock": ("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", {}),
    "cerebras": ("cerebras/llama3.1-8b", {}),
    "xiaomi_mimo": ("xiaomi_mimo/mimo-v2-flash", {}),
    "openai_like": ("openai/some-model", {}),  # gateways reached through an api_base only
    "gemini_like": ("gemini/gemini-2.5-pro", {}),
    "anthropic_like": ("anthropic/claude-sonnet-4-5", {}),
}
BASE_SCENARIOS = (
    "basic",
    "tools",
    "reasoning_high",
    "json_schema",
    "extra_body",
    "image",
    "headers",
    "stream",
    "tool_history",
    "cache_control",
    "reasoning_tools",
)
RESPONSES_PROVIDERS = frozenset({"openai", "openai_gpt5", "openai_like", "xai", "deepseek", "openrouter"})
RESPONSES_SCENARIOS = ("responses", "responses_stream", "responses_tools")
ANTHROPIC_WIRE_PROVIDERS = frozenset({"openai_like"})
ANTHROPIC_WIRE_SCENARIOS = ("anthropic_wire", "anthropic_wire_stream", "anthropic_wire_tools")
_TOOL_SCENARIOS = frozenset({"tools", "tool_history", "reasoning_tools", "responses_tools", "anthropic_wire_tools"})
_HISTORY_SCENARIOS = frozenset({"tool_history", "reasoning_tools", "responses_tools", "anthropic_wire_tools"})


def _canned(request: httpx.Request) -> httpx.Response:
    """A valid answer in the protocol the request addresses."""
    path = urlsplit(str(request.url)).path
    try:
        body = json.loads(request.content or b"{}")
    except ValueError:
        body = {}
    stream = bool(body.get("stream")) or "streamGenerateContent" in path
    sse = {"content-type": "text/event-stream"}
    plain = {"content-type": "application/json"}

    def answer(streamed: str, whole: object) -> httpx.Response:
        return httpx.Response(
            200,
            content=streamed if stream else json.dumps(whole),
            headers=sse if stream else plain,
            request=request,
        )

    if path.endswith("/responses"):
        return answer(_RESPONSES_SSE, _RESPONSES_JSON)
    if path.endswith("/messages") and ("anthropic-version" in request.headers or "x-api-key" in request.headers):
        return answer(_ANTHROPIC_SSE, _ANTHROPIC_JSON)
    if "generateContent" in path or "streamGenerateContent" in path:
        return answer(f"data: {json.dumps(_GEMINI_JSON)}\n\n", _GEMINI_JSON)
    if path.endswith("/api/chat"):
        return httpx.Response(
            200, content=_OLLAMA_CHAT_NDJSON, headers={"content-type": "application/x-ndjson"}, request=request
        )
    return answer(_CHAT_SSE, _CHAT_JSON)


def _record(request: httpx.Request) -> Record:
    try:
        body: object = json.loads(request.content) if request.content else None
    except ValueError:
        body = {"__raw_len__": len(request.content or b"")}
    headers: dict[str, str] = {}
    for name, value in request.headers.items():
        key = name.lower()
        if key in _IGNORED_HEADERS or not key.startswith(_KEPT_HEADER_PREFIXES):
            continue
        headers[key] = f"<redacted:{value.split(' ')[0]}>" if key in _SECRET_HEADERS else value
    split = urlsplit(str(request.url))
    return {
        "method": request.method,
        "url": f"{split.scheme}://{split.netloc}{split.path}",
        "query": split.query,
        "headers": headers,
        "body": body,
    }


def _messages(scenario: str) -> list[BaseMessage]:
    if scenario in _HISTORY_SCENARIOS:
        call = {"name": "get_weather", "args": {"city": "Paris"}, "id": "call_1", "type": "tool_call"}
        return [
            SystemMessage(content="Be brief."),
            HumanMessage(content="weather in Paris?"),
            AIMessage(content="", tool_calls=[call]),
            ToolMessage(content="sunny", tool_call_id="call_1"),
            HumanMessage(content="thanks"),
        ]
    if scenario == "cache_control":
        mark = {"cache_control": {"type": "ephemeral"}}
        return [
            SystemMessage(content=[{"type": "text", "text": "Be brief.", **mark}]),
            HumanMessage(content=[{"type": "text", "text": "hi", **mark}]),
        ]
    if scenario == "image":
        picture = {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo=", "detail": "auto"}}
        return [
            SystemMessage(content="Be brief."),
            HumanMessage(content=[{"type": "text", "text": "what is this"}, picture]),
        ]
    return [SystemMessage(content="Be brief."), HumanMessage(content="hi")]


def _model_kwargs(extra: Mapping[str, object]) -> dict[str, object]:
    raw = extra.get("model_kwargs")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _factory_kwargs(extra: Mapping[str, object], with_base: bool, scenario: str) -> dict[str, object]:
    kwargs: dict[str, object] = {"api_key": "sk-golden-test-key", "temperature": 0.2, "max_tokens": 128, **extra}
    if with_base:
        kwargs["base_url"] = _BASE_URL
    if scenario in ("reasoning_high", "reasoning_tools"):
        kwargs.update(reasoning_effort="high", max_tokens=4096)
    if scenario.startswith("responses"):
        kwargs["wire_protocol"] = "responses"
    if scenario.startswith("anthropic_wire"):
        kwargs["wire_protocol"] = "anthropic_messages"
    if scenario == "extra_body":
        kwargs["extra_body"] = {"foo": "bar"}
    if scenario == "headers":
        kwargs["model_kwargs"] = {**_model_kwargs(extra), "extra_headers": {"X-Test": "1"}}
    return kwargs


async def _run_case(
    model: str, extra: Mapping[str, object], with_base: bool, scenario: str, sink: list[Record]
) -> Case:
    sink.clear()
    error = ""
    try:
        llm = create_chat_model(
            model, streaming=scenario.endswith("stream"), **_factory_kwargs(extra, with_base, scenario)
        )
        runnable = llm
        if scenario in _TOOL_SCENARIOS:
            runnable = llm.bind_tools(_TOOLS, tool_choice="auto", parallel_tool_calls=True)
        elif scenario == "json_schema":
            runnable = llm.bind(response_format=_JSON_SCHEMA)
        if scenario.endswith("stream"):
            async for _ in runnable.astream(_messages(scenario)):
                pass
        else:
            await runnable.ainvoke(_messages(scenario))
    except Exception as exc:  # the request is already recorded; failures to read the canned answer are irrelevant here
        error = f"{type(exc).__name__}: {str(exc)[:140]}"
    return {"requests": list(sink), "error": error}


def case_keys(only: frozenset[str] | None = None) -> list[tuple[str, bool, str]]:
    """(provider, with_base, scenario) of every case in matrix order."""
    keys: list[tuple[str, bool, str]] = []
    for provider in PROVIDERS:
        if only is not None and provider not in only:
            continue
        for with_base in (False, True):
            if provider == "openai_like" and not with_base:
                continue
            scenarios = list(BASE_SCENARIOS)
            if provider in RESPONSES_PROVIDERS:
                scenarios += RESPONSES_SCENARIOS
            if provider in ANTHROPIC_WIRE_PROVIDERS:
                scenarios += ANTHROPIC_WIRE_SCENARIOS
            keys.extend((provider, with_base, scenario) for scenario in scenarios)
    return keys


def case_name(provider: str, with_base: bool, scenario: str) -> str:
    return f"{provider}|{'custom_base' if with_base else 'default_base'}|{scenario}"


def install_recorder(monkeypatch: pytest.MonkeyPatch) -> list[Record]:
    """Replace ``httpx`` ``send`` so every request is recorded and answered with a canned provider response."""
    sink: list[Record] = []

    async def async_send(self: httpx.AsyncClient, request: httpx.Request, **kwargs: object) -> httpx.Response:
        sink.append(_record(request))
        return _canned(request)

    def sync_send(self: httpx.Client, request: httpx.Request, **kwargs: object) -> httpx.Response:
        sink.append(_record(request))
        return _canned(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", async_send)
    monkeypatch.setattr(httpx.Client, "send", sync_send)
    return sink


def capture_all(sink: list[Record], only: frozenset[str] | None = None) -> dict[str, Case]:
    """Run the matrix; ``sink`` is the list ``install_recorder`` returned."""

    async def main() -> dict[str, Case]:
        cases: dict[str, Case] = {}
        for provider, with_base, scenario in case_keys(only):
            model, extra = PROVIDERS[provider]
            cases[case_name(provider, with_base, scenario)] = await _run_case(model, extra, with_base, scenario, sink)
        return cases

    return asyncio.run(main())
