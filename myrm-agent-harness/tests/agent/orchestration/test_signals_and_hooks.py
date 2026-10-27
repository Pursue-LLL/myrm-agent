"""Unit tests for agent.orchestration signals and the registry's runtime-only tools."""

from __future__ import annotations

from myrm_agent_harness.agent.orchestration.signals.catalog import (
    DEEP_RESEARCH_SIGNAL_NAMES,
    ORCHESTRATION_SIGNAL_NAMES,
    VERIFIER_SIGNAL_NAMES,
)
from myrm_agent_harness.agent.orchestration.signals.deep_research import (
    DISPATCH_TOOL_NAME,
    FINALIZE_TOOL_NAME,
    THINK_TOOL_NAME,
    DispatchResearchInput,
    build_orchestrator_tools,
    build_signal_schema,
)
from myrm_agent_harness.agent.orchestration.signals.verifier import (
    SUBMIT_VERDICT_SIGNAL_NAME,
    create_submit_verdict_tool,
)
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolBindMode, ToolSource


def test_orchestration_signal_names_are_the_union_of_their_groups() -> None:
    assert DEEP_RESEARCH_SIGNAL_NAMES | VERIFIER_SIGNAL_NAMES == ORCHESTRATION_SIGNAL_NAMES


def test_build_signal_schema_shape() -> None:
    schema = build_signal_schema(
        DISPATCH_TOOL_NAME,
        "Dispatch research sub-agent",
        DispatchResearchInput,
    )
    assert schema["type"] == "function"
    function = schema["function"]
    assert function["name"] == DISPATCH_TOOL_NAME
    assert function["description"] == "Dispatch research sub-agent"
    params = function["parameters"]
    assert "properties" in params
    assert "task" in params["properties"]
    assert "title" not in params


def test_build_orchestrator_tools_include_think() -> None:
    tools = build_orchestrator_tools(include_think=True)
    names = [tool["function"]["name"] for tool in tools]
    assert names == [DISPATCH_TOOL_NAME, THINK_TOOL_NAME, FINALIZE_TOOL_NAME]


def test_build_orchestrator_tools_exclude_think() -> None:
    tools = build_orchestrator_tools(include_think=False)
    names = [tool["function"]["name"] for tool in tools]
    assert names == [DISPATCH_TOOL_NAME, FINALIZE_TOOL_NAME]


def test_create_submit_verdict_tool_writes_context() -> None:
    context: dict[str, object] = {}
    verdict_tool = create_submit_verdict_tool(context)
    assert verdict_tool.name == SUBMIT_VERDICT_SIGNAL_NAME

    result = verdict_tool.invoke(
        {
            "passed": True,
            "summary": "All checks passed",
            "findings": [{"severity": "info", "detail": "none"}],
            "confidence": "HIGH",
        }
    )
    assert result == "Verdict submitted successfully. Please complete your response."
    verdict = context["_verifier_verdict"]
    assert verdict.passed is True
    assert verdict.summary == "All checks passed"
    assert verdict.confidence == "HIGH"


class TestRuntimeOnlyTool:
    def test_a_runtime_only_tool_is_executable_but_never_bound_on_the_first_turn(self) -> None:
        from langchain_core.tools import tool

        @tool("_middleware_injected")
        def _middleware_injected(reason: str = "") -> str:
            """A tool a middleware injects as a tool call."""
            return reason or "ok"

        reg = ToolRegistry()
        reg.register(_middleware_injected, source=ToolSource.MIDDLEWARE, bind_mode=ToolBindMode.RUNTIME_ONLY)
        assert reg.has_tool("_middleware_injected")
        assert "_middleware_injected" in {tool.name for tool in reg.get_runtime_tools()}
        assert "_middleware_injected" not in {tool.name for tool in reg.resolve()}
