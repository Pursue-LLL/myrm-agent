"""Deep Research vs General Agent real-world comparison test.

Uses the same research query to compare:
1. General Agent via HTTP SSE endpoint
2. Deep Research Orchestrator direct invocation

Requires BASIC_API_KEY environment variable to run.
"""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection, get_search_service_config

BASIC_API_KEY = os.getenv("BASIC_API_KEY")
BASIC_MODEL = os.getenv("BASIC_MODEL")
if not BASIC_MODEL:
    raise RuntimeError("BASIC_MODEL must be set")
BASIC_BASE_URL = os.getenv("BASIC_BASE_URL")

RESEARCH_QUERY = "2024-2025年大语言模型在代码生成领域有哪些重要进展？请列出关键技术突破和代表性模型。"


def _collect_general_agent_response(client: TestClient, query: str) -> dict[str, object]:
    """Run General Agent via HTTP and collect SSE events."""
    request_body: dict[str, object] = {
        "query": query,
        "messageId": f"msg-{int(time.time() * 1000)}",
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
    }

    start = time.monotonic()
    message_chunks: list[str] = []
    events: list[dict[str, object]] = []
    tool_calls = 0
    has_sources = False

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as resp:
        if resp.status_code != 200:
            resp.read()
            return {"error": f"HTTP {resp.status_code}: {resp.text}", "elapsed": 0}

        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                events.append(data)
                evt_type = data.get("type", "")
                if evt_type == "message":
                    content = data.get("data", "")
                    if content:
                        message_chunks.append(str(content))
                elif evt_type == "sources":
                    has_sources = True
                elif evt_type == "tasks_steps" and data.get("tool_name"):
                    tool_calls += 1
            except json.JSONDecodeError:
                pass

    elapsed = time.monotonic() - start
    answer = "".join(message_chunks)

    return {
        "answer": answer,
        "answer_length": len(answer),
        "event_count": len(events),
        "tool_calls": tool_calls,
        "has_sources": has_sources,
        "elapsed_seconds": round(elapsed, 2),
        "error": None,
    }


def _build_search_tools() -> list:
    """Build web search tools using env config, matching General Agent setup."""
    from myrm_agent_harness.toolkits import create_web_search_tool
    from myrm_agent_harness.toolkits.web_search.web_searcher import SearchServiceConfig

    search_service = os.getenv("SEARCH_SERVICE", "tavily")
    api_key = os.getenv("TAVILY_API_KEY", "")

    if not api_key:
        return []

    cfg = SearchServiceConfig(
        search_service=search_service,
        api_key=api_key,
        api_base=os.getenv("SEARXNG_URL"),
    )
    return [create_web_search_tool(cfg)]


async def _collect_deep_research_response(query: str) -> dict[str, object]:
    """Run Deep Research Orchestrator directly and collect events."""
    from myrm_agent_harness.agent.deep_research import (
        DeepResearchConfig,
        DeepResearchOrchestrator,
    )
    from myrm_agent_harness.agent.streaming.types import AgentEventType
    from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model

    from tests.api.agent.utils import _convert_litellm_model

    llm = create_litellm_model(
        model=_convert_litellm_model(BASIC_MODEL),
        api_key=BASIC_API_KEY,
        base_url=BASIC_BASE_URL,
        temperature=0.3,
        streaming=True,
    )

    config = DeepResearchConfig(
        max_cycles=2,
        max_concurrent_agents=2,
        enable_clarification=False,
        max_duration_seconds=180,
        llm_call_timeout_seconds=60,
        report_timeout_seconds=60,
    )

    context: dict[str, object] = {
        "session_id": "test-user_test-chat",
    }

    parent_tools = _build_search_tools()
    orch = DeepResearchOrchestrator(llm=llm, config=config, context=context, parent_tools=parent_tools)

    start = time.monotonic()
    events: list[dict[str, object]] = []
    phases_seen: list[str] = []

    try:
        async for event in orch.run(query, message_id="test-comparison", context=context):
            events.append(event)
            evt_type = event.get("type", "")
            step_key = event.get("step_key", "")
            if evt_type == AgentEventType.TASKS_STEPS.value and step_key:
                phases_seen.append(str(step_key))
    except Exception as e:
        return {"error": str(e), "elapsed_seconds": round(time.monotonic() - start, 2)}

    elapsed = time.monotonic() - start
    result = orch.result

    return {
        "answer": result.report,
        "answer_length": len(result.report),
        "event_count": len(events),
        "cycle_count": result.cycle_count,
        "phases": phases_seen,
        "has_plan": bool(result.research_plan),
        "plan_length": len(result.research_plan),
        "agent_results_count": len(result.agent_results),
        "total_input_tokens": result.total_input_tokens,
        "total_output_tokens": result.total_output_tokens,
        "estimated_cost_usd": result.estimated_cost_usd,
        "elapsed_seconds": round(elapsed, 2),
        "was_cancelled": result.was_cancelled,
        "error": result.error,
    }


@pytest.mark.e2e
@pytest.mark.skipif(
    not BASIC_API_KEY,
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestDeepResearchVsGeneral:
    """Compare General Agent and Deep Research on the same query."""

    def test_general_agent_research(self, client: TestClient) -> None:
        """General Agent handles a research query."""
        result = _collect_general_agent_response(client, RESEARCH_QUERY)

        if result.get("error"):
            error_msg = str(result["error"])
            if any(kw in error_msg for kw in ["Authentication", "Connection", "InternalServerError"]):
                pytest.skip(f"Environment issue: {error_msg[:100]}")
            else:
                pytest.fail(f"Agent error: {error_msg}")

        print(f"\n{'=' * 60}")
        print("General Agent Results:")
        print(f"  Answer length: {result['answer_length']} chars")
        print(f"  Events: {result['event_count']}")
        print(f"  Tool calls: {result['tool_calls']}")
        print(f"  Has sources: {result['has_sources']}")
        print(f"  Elapsed: {result['elapsed_seconds']}s")
        print(f"{'=' * 60}")

        assert result["event_count"] > 0

    @pytest.mark.asyncio
    async def test_deep_research(self) -> None:
        """Deep Research Orchestrator handles the same query."""
        result = await _collect_deep_research_response(RESEARCH_QUERY)

        print(f"\n{'=' * 60}")
        print("Deep Research Results:")
        print(f"  Answer length: {result.get('answer_length', 0)} chars")
        print(f"  Events: {result.get('event_count', 0)}")
        print(f"  Cycles: {result.get('cycle_count', 0)}")
        print(f"  Phases: {result.get('phases', [])}")
        print(f"  Has plan: {result.get('has_plan', False)}")
        print(f"  Plan length: {result.get('plan_length', 0)} chars")
        print(f"  Agent results: {result.get('agent_results_count', 0)}")
        print(f"  Tokens: {result.get('total_input_tokens', 0)} in / {result.get('total_output_tokens', 0)} out")
        print(f"  Cost: ${result.get('estimated_cost_usd', 0):.4f}")
        print(f"  Elapsed: {result.get('elapsed_seconds', 0)}s")
        print(f"{'=' * 60}")

        if result.get("error"):
            error_str = str(result["error"])
            if any(kw in error_str for kw in ["Authentication", "Connection", "timeout"]):
                pytest.skip(f"Environment issue: {error_str[:100]}")
            else:
                pytest.fail(f"Deep Research error: {error_str}")

        assert result.get("event_count", 0) > 0
        assert result.get("has_plan") is True
        assert "deep_research_planning" in result.get("phases", [])
        assert "deep_research_report" in result.get("phases", [])

    @pytest.mark.asyncio
    async def test_comparison_summary(self, client: TestClient) -> None:
        """Run both and print comparison summary."""
        general_result = _collect_general_agent_response(client, RESEARCH_QUERY)
        deep_result = await _collect_deep_research_response(RESEARCH_QUERY)

        print(f"\n{'=' * 70}")
        print(f"{'COMPARISON: General Agent vs Deep Research':^70}")
        print(f"{'=' * 70}")
        print(f"Query: {RESEARCH_QUERY[:60]}...")
        print(f"Model: {BASIC_MODEL}")
        print(f"{'-' * 70}")
        print(f"{'Metric':<30} {'General':>15} {'Deep Research':>15}")
        print(f"{'-' * 70}")
        print(
            f"{'Answer length (chars)':<30} {general_result.get('answer_length', 0):>15} {deep_result.get('answer_length', 0):>15}"
        )
        print(f"{'Event count':<30} {general_result.get('event_count', 0):>15} {deep_result.get('event_count', 0):>15}")
        print(f"{'Tool calls / Cycles':<30} {general_result.get('tool_calls', 0):>15} {deep_result.get('cycle_count', 0):>15}")
        print(
            f"{'Has sources / Has plan':<30} {str(general_result.get('has_sources', False)):>15} {str(deep_result.get('has_plan', False)):>15}"
        )
        print(
            f"{'Elapsed (seconds)':<30} {general_result.get('elapsed_seconds', 0):>15} {deep_result.get('elapsed_seconds', 0):>15}"
        )

        if deep_result.get("total_input_tokens"):
            print(f"{'Input tokens':<30} {'N/A':>15} {deep_result.get('total_input_tokens', 0):>15}")
            print(f"{'Output tokens':<30} {'N/A':>15} {deep_result.get('total_output_tokens', 0):>15}")
            print(f"{'Estimated cost':<30} {'N/A':>15} ${deep_result.get('estimated_cost_usd', 0):.4f}")

        print(f"{'-' * 70}")
        print(f"{'Deep Research phases:':<30} {', '.join(deep_result.get('phases', []))}")
        print(f"{'Agent results count:':<30} {deep_result.get('agent_results_count', 0)}")
        print(f"{'=' * 70}")

        if general_result.get("error") or deep_result.get("error"):
            gen_err = general_result.get("error", "None")
            deep_err = deep_result.get("error", "None")
            if any(kw in str(gen_err) + str(deep_err) for kw in ["Authentication", "Connection", "timeout"]):
                pytest.skip(f"Environment issue: general={gen_err}, deep={deep_err}")

        assert general_result.get("event_count", 0) > 0 or deep_result.get("event_count", 0) > 0
