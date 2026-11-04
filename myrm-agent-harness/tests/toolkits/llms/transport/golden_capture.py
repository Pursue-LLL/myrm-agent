"""Records the outbound HTTP requests of the real model factory and adapter for a fixed scenario matrix.

[INPUT]
- core.llm::create_chat_model (POS: the production model factory)
- httpx (POS: patched ``send`` that records the request and answers with a canned, valid provider response)

[OUTPUT]
- capture_all: {"provider|base|scenario": {"requests": [...], "error": str}} for every provider x scenario

[POS]
Library-agnostic request capture. The committed baseline ``golden_baseline.json`` was recorded the same way at
commit b6959e7d7e, when the factory still called the previous multi-provider client library (litellm 1.97.0) with
the production configuration applied; the golden test replays the matrix on the current transport and diffs the two.
Only the final request on the wire is observed, so the comparison does not depend on any library internals.

The matrix has three parts: every provider against the base scenarios (plus the Responses and Anthropic-wire ones
where the provider has them), one model of each capability family that changes how a request is built (``VARIANTS``:
sampling parameters, reasoning effort, tool-call history), and requests the providers' APIs are strict about
(``EDGE_SCENARIOS``: blank text, parallel tool results, a closing assistant message, an image in a tool result, JSON
output beside tools).
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

from .event_stream_bodies import CONTENT_TYPE as EVENT_STREAM
from .event_stream_bodies import converse_answer, text_stream
from .golden_recorder import Case, Record, install_request_recorder

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
    "yunshu": ("yunshu/gpt-4o-mini", {}),
    "openai_like": ("openai/some-model", {}),  # gateways reached through an api_base only
    "gemini_like": ("gemini/gemini-2.5-pro", {}),
    "anthropic_like": ("anthropic/claude-sonnet-4-5", {}),
}
# One model of each capability family that changes how a request is built (sampling parameters, reasoning effort,
# tool-call history). They share their provider's endpoint, so only the scenarios those rules touch are run.
VARIANTS: dict[str, tuple[str, dict[str, object]]] = {
    "anthropic_opus45": ("anthropic/claude-opus-4-5", {}),
    "anthropic_sonnet46": ("anthropic/claude-sonnet-4-6", {}),
    "anthropic_opus47": ("anthropic/claude-opus-4-7", {}),
    "anthropic_haiku45": ("anthropic/claude-haiku-4-5", {}),
    "gemini25pro": ("gemini/gemini-2.5-pro", {}),
    "gemini25flashlite": ("gemini/gemini-2.5-flash-lite", {}),
    "gemini3": ("gemini/gemini-3-pro-preview", {}),
    "gemini31": ("gemini/gemini-3.1-pro-preview", {}),
    "gemini3flash": ("gemini/gemini-3-flash-preview", {}),
    "openai_gpt51": ("openai/gpt-5.1", {}),
    "openai_gpt52": ("openai/gpt-5.2", {}),
}
PROVIDERS.update(VARIANTS)
# One model of each Bedrock family that builds its request differently: whether it takes tools and a tool choice,
# how it reasons, whether it has a native structured-output format, which sampling fields it reads. They share the
# ``bedrock`` provider's endpoint and run ``BEDROCK_SCENARIOS``.
BEDROCK_VARIANTS: dict[str, tuple[str, dict[str, object]]] = {
    "bedrock_claude35": ("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", {}),
    "bedrock_claude37": ("bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0", {}),
    "bedrock_claude45": ("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0", {}),
    "bedrock_haiku45": ("bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0", {}),
    "bedrock_opus45": ("bedrock/us.anthropic.claude-opus-4-5-20251101-v1:0", {}),
    "bedrock_sonnet46": ("bedrock/us.anthropic.claude-sonnet-4-6", {}),
    "bedrock_opus47": ("bedrock/us.anthropic.claude-opus-4-7", {}),
    "bedrock_nova": ("bedrock/amazon.nova-pro-v1:0", {}),
    "bedrock_nova2": ("bedrock/us.amazon.nova-2-lite-v1:0", {}),
    "bedrock_gptoss": ("bedrock/openai.gpt-oss-120b-1:0", {}),
    "bedrock_llama33": ("bedrock/us.meta.llama3-3-70b-instruct-v1:0", {}),
    "bedrock_llama3": ("bedrock/meta.llama3-70b-instruct-v1:0", {}),
    "bedrock_mistral": ("bedrock/mistral.mistral-large-2407-v1:0", {}),
    "bedrock_deepseek": ("bedrock/us.deepseek.r1-v1:0", {}),
    "bedrock_arn": ("bedrock/arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123", {}),
}
PROVIDERS.update(BEDROCK_VARIANTS)
# Reasoning efforts other than the base matrix's ``high``: how each maps to a budget, a level or a switch-off differs
# by model, so every variant and one model of each other reasoning family run them.
EFFORT_SCENARIOS = ("reasoning_minimal", "reasoning_medium", "reasoning_none")
EFFORT_PROVIDERS = frozenset({"anthropic", "gemini", "openai_gpt5", "openai_o3", "deepseek", "deepseek_reasoner"})
_EFFORT_OF_SCENARIO = {
    "reasoning_high": "high",
    "reasoning_tools": "high",
    "reasoning_required": "high",
    "reasoning_xhigh": "xhigh",
    "reasoning_minimal": "minimal",
    "reasoning_medium": "medium",
    "reasoning_none": "none",
    "json_schema_reasoning": "high",
    "tools_json_reasoning": "high",
}
VARIANT_SCENARIOS = (
    "basic",
    "defaults",
    "sampling",
    "tools",
    "reasoning_high",
    "reasoning_xhigh",
    *EFFORT_SCENARIOS,
    "stream",
    "tool_history",
    "tool_history_unbound",
    "tool_history_foreign_ids",
    "reasoning_tools",
)
# What a Bedrock family changes: the tool choice (stated, forced, named), a forced choice beside reasoning, the
# structured answer alone and beside tools with and without reasoning, the caller's extra fields and cache marks.
BEDROCK_SCENARIOS = (
    *VARIANT_SCENARIOS,
    "tools_required",
    "tools_named",
    "reasoning_required",
    "json_schema",
    "tools_json_output",
    "json_schema_reasoning",
    "tools_json_reasoning",
    "extra_body",
    "cache_control",
)
BASE_SCENARIOS = (
    "basic",
    "defaults",
    "sampling",
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
# Requests the providers' APIs are strict about: blank text, parallel tool results, a closing assistant message, an
# image in a tool result, JSON output beside tools. Run on one provider per message translation (OpenAI-compatible,
# Anthropic, Gemini, Ollama) at its default endpoint.
EDGE_PROVIDERS = frozenset({"openai", "deepseek", "anthropic", "anthropic_opus47", "gemini", "gemini3", "ollama"})
EDGE_SCENARIOS = (
    "history_blank_assistant",
    "history_blank_assistant_tool",
    "history_blank_user",
    "history_parallel_tools",
    "history_prefill_space",
    "history_empty_tool_result",
    "history_tool_image",
    "tools_json_output",
)
RESPONSES_PROVIDERS = frozenset({"openai", "openai_gpt5", "openai_like", "xai", "deepseek", "openrouter"})
RESPONSES_SCENARIOS = ("responses", "responses_stream", "responses_tools")
ANTHROPIC_WIRE_PROVIDERS = frozenset({"openai_like"})
ANTHROPIC_WIRE_SCENARIOS = ("anthropic_wire", "anthropic_wire_stream", "anthropic_wire_tools")
# Scenarios that state a tool choice other than ``auto`` on a fresh conversation (no replayed tool call).
_CHOICE_OF_SCENARIO: dict[str, str | dict[str, object]] = {
    "tools_required": "required",
    "tools_named": {"type": "function", "function": {"name": "get_weather"}},
    "reasoning_required": "required",
}
_TOOL_SCENARIOS = frozenset(
    {
        *_CHOICE_OF_SCENARIO,
        "tools",
        "tool_history",
        "tool_history_foreign_ids",
        "reasoning_tools",
        "responses_tools",
        "anthropic_wire_tools",
        "history_blank_assistant_tool",
        "history_parallel_tools",
        "history_empty_tool_result",
        "history_tool_image",
        "tools_json_output",
        "tools_json_reasoning",
    }
)
# The history replays a tool call and its result; ``tool_history_unbound`` sends it without any tool definition.
_HISTORY_SCENARIOS = _TOOL_SCENARIOS - {"tools", "tools_json_reasoning", *_CHOICE_OF_SCENARIO} | {
    "tool_history_unbound"
}
# Tool-call ids another provider minted (Kimi style: dots and a colon), replayed into this provider.
_FOREIGN_CALL_ID = "functions.get_weather:0"


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
    if path.endswith("/converse"):
        return httpx.Response(200, json=converse_answer({"text": "ok"}), request=request)
    if path.endswith("/converse-stream"):
        content = b"".join(text_stream("ok"))
        return httpx.Response(200, content=content, headers={"content-type": EVENT_STREAM}, request=request)
    return answer(_CHAT_SSE, _CHAT_JSON)


def _tool_call(index: int, city: str) -> dict[str, object]:
    return {"name": "get_weather", "args": {"city": city}, "id": f"call_{index}", "type": "tool_call"}


def _edge_messages(scenario: str) -> list[BaseMessage]:
    system, asked = SystemMessage(content="Be brief."), HumanMessage(content="weather?")
    if scenario == "history_blank_assistant":
        return [system, HumanMessage(content="hi"), AIMessage(content="  \n"), HumanMessage(content="thanks")]
    if scenario == "history_blank_assistant_tool":
        return [
            system,
            asked,
            AIMessage(content="\n\n", tool_calls=[_tool_call(1, "Paris")]),
            ToolMessage(content="sunny", tool_call_id="call_1"),
            HumanMessage(content="thanks"),
        ]
    if scenario == "history_blank_user":
        return [system, HumanMessage(content="   ")]
    if scenario == "history_parallel_tools":
        return [
            system,
            asked,
            AIMessage(content="Checking.", tool_calls=[_tool_call(1, "Paris"), _tool_call(2, "Rome")]),
            ToolMessage(content="sunny", tool_call_id="call_1"),
            ToolMessage(content="rainy", tool_call_id="call_2"),
            HumanMessage(content="thanks"),
        ]
    if scenario == "history_prefill_space":
        return [system, HumanMessage(content="hi"), AIMessage(content="Hello there. ")]
    if scenario == "history_tool_image":
        screenshot = {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}}
        return [
            system,
            asked,
            AIMessage(content="", tool_calls=[_tool_call(1, "Paris")]),
            ToolMessage(content=[{"type": "text", "text": "shot"}, screenshot], tool_call_id="call_1"),
        ]
    if scenario == "tools_json_output":
        return [system, asked]
    return [  # history_empty_tool_result
        system,
        asked,
        AIMessage(content="", tool_calls=[_tool_call(1, "Paris")]),
        ToolMessage(content="", tool_call_id="call_1"),
    ]


def _messages(scenario: str) -> list[BaseMessage]:
    if scenario in EDGE_SCENARIOS:
        return _edge_messages(scenario)
    if scenario in _HISTORY_SCENARIOS:
        call_id = _FOREIGN_CALL_ID if scenario == "tool_history_foreign_ids" else "call_1"
        call = {"name": "get_weather", "args": {"city": "Paris"}, "id": call_id, "type": "tool_call"}
        return [
            SystemMessage(content="Be brief."),
            HumanMessage(content="weather in Paris?"),
            AIMessage(content="", tool_calls=[call]),
            ToolMessage(content="sunny", tool_call_id=call_id),
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
    if scenario == "sampling":  # the sampling options a user can put in a model configuration
        kwargs.update(top_p=0.9, top_k=40)
        kwargs["model_kwargs"] = {**_model_kwargs(extra), "seed": 7, "frequency_penalty": 0.1, "stop": ["END"]}
    if scenario == "defaults":  # what each provider adds when the caller sets no sampling parameter at all
        del kwargs["temperature"], kwargs["max_tokens"]
    if with_base:
        kwargs["base_url"] = _BASE_URL
    if scenario in _EFFORT_OF_SCENARIO:
        kwargs.update(reasoning_effort=_EFFORT_OF_SCENARIO[scenario], max_tokens=4096)
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
            choice = _CHOICE_OF_SCENARIO.get(scenario, "auto")
            runnable = llm.bind_tools(_TOOLS, tool_choice=choice, parallel_tool_calls=True)
            if scenario in ("tools_json_output", "tools_json_reasoning"):
                runnable = runnable.bind(response_format=_JSON_SCHEMA)
        elif scenario in ("json_schema", "json_schema_reasoning"):
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
        if provider in BEDROCK_VARIANTS:
            keys.extend((provider, False, scenario) for scenario in BEDROCK_SCENARIOS)
            continue
        if provider in VARIANTS:
            keys.extend((provider, False, scenario) for scenario in VARIANT_SCENARIOS)
            if provider in EDGE_PROVIDERS:
                keys.extend((provider, False, scenario) for scenario in EDGE_SCENARIOS)
            continue
        for with_base in (False, True):
            if provider == "openai_like" and not with_base:
                continue
            scenarios = list(BASE_SCENARIOS)
            if provider in EDGE_PROVIDERS and not with_base:
                scenarios += EDGE_SCENARIOS
            if provider in EFFORT_PROVIDERS and not with_base:
                scenarios += EFFORT_SCENARIOS
            if provider in RESPONSES_PROVIDERS:
                scenarios += RESPONSES_SCENARIOS
            if provider in ANTHROPIC_WIRE_PROVIDERS:
                scenarios += ANTHROPIC_WIRE_SCENARIOS
            keys.extend((provider, with_base, scenario) for scenario in scenarios)
    return keys


def case_name(provider: str, with_base: bool, scenario: str) -> str:
    return f"{provider}|{'custom_base' if with_base else 'default_base'}|{scenario}"


def install_recorder(monkeypatch: pytest.MonkeyPatch) -> list[Record]:
    """Record every request of the chat matrix and answer it with a canned chat provider response."""
    return install_request_recorder(monkeypatch, _canned)


def capture_all(sink: list[Record], only: frozenset[str] | None = None) -> dict[str, Case]:
    """Run the matrix; ``sink`` is the list ``install_recorder`` returned."""

    async def main() -> dict[str, Case]:
        cases: dict[str, Case] = {}
        for provider, with_base, scenario in case_keys(only):
            model, extra = PROVIDERS[provider]
            cases[case_name(provider, with_base, scenario)] = await _run_case(model, extra, with_base, scenario, sink)
        return cases

    return asyncio.run(main())
