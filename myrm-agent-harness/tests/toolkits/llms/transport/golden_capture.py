"""Records the outbound HTTP requests of the real model factory and adapter for a fixed scenario matrix.

[INPUT]
- core.llm::create_chat_model (POS: the production model factory)
- golden_matrix (POS: the providers, scenarios and what each scenario sends)
- golden_canned::canned_answer (POS: a valid answer in the protocol each request addresses)
- golden_recorder::install_request_recorder (POS: patched ``send`` that records the request)

[OUTPUT]
- capture_all: {"provider|base|scenario": {"requests": [...], "error": str}} for every provider x scenario
- install_recorder: the recorder to pass to ``capture_all``

[POS]
Library-agnostic request capture. The committed baseline ``golden_baseline.json`` was recorded the same way at
commit b6959e7d7e, when the factory called the multi-provider litellm client library (litellm 1.97.0) with
the production configuration applied; the golden test replays the matrix on the current transport and diffs the two.
Only the final request on the wire is observed, so the comparison does not depend on any library internals.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model

from .golden_canned import canned_answer
from .golden_matrix import (
    BASE_URL,
    CHOICE_OF_SCENARIO,
    EDGE_SCENARIOS,
    EFFORT_OF_SCENARIO,
    FOREIGN_CALL_ID,
    HISTORY_SCENARIOS,
    JSON_SCHEMA,
    PROVIDERS,
    TOOL_SCENARIOS,
    TOOLS,
    case_keys,
    case_name,
)
from .golden_recorder import Case, Record, install_request_recorder


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
    if scenario in HISTORY_SCENARIOS:
        call_id = FOREIGN_CALL_ID if scenario == "tool_history_foreign_ids" else "call_1"
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
        kwargs["base_url"] = BASE_URL
    if scenario in EFFORT_OF_SCENARIO:
        kwargs.update(reasoning_effort=EFFORT_OF_SCENARIO[scenario], max_tokens=4096)
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
        if scenario in TOOL_SCENARIOS:
            choice = CHOICE_OF_SCENARIO.get(scenario, "auto")
            runnable = llm.bind_tools(TOOLS, tool_choice=choice, parallel_tool_calls=True)
            if scenario in ("tools_json_output", "tools_json_reasoning"):
                runnable = runnable.bind(response_format=JSON_SCHEMA)
        elif scenario in ("json_schema", "json_schema_reasoning"):
            runnable = llm.bind(response_format=JSON_SCHEMA)
        if scenario.endswith("stream"):
            async for _ in runnable.astream(_messages(scenario)):
                pass
        else:
            await runnable.ainvoke(_messages(scenario))
    except Exception as exc:  # the request is already recorded; failures to read the canned answer are irrelevant here
        error = f"{type(exc).__name__}: {str(exc)[:140]}"
    return {"requests": list(sink), "error": error}


def install_recorder(monkeypatch: pytest.MonkeyPatch) -> list[Record]:
    """Record every request of the chat matrix and answer it with a canned chat provider response."""
    return install_request_recorder(monkeypatch, canned_answer)


def capture_all(sink: list[Record], only: frozenset[str] | None = None) -> dict[str, Case]:
    """Run the matrix; ``sink`` is the list ``install_recorder`` returned."""

    async def main() -> dict[str, Case]:
        cases: dict[str, Case] = {}
        for provider, with_base, scenario in case_keys(only):
            model, extra = PROVIDERS[provider]
            cases[case_name(provider, with_base, scenario)] = await _run_case(model, extra, with_base, scenario, sink)
        return cases

    return asyncio.run(main())
