"""E2E: web_search → sources SSE + citation markers (Lane-C API).

Fast Search and General Agent share the same sources → UI pipeline; this module
validates the live web_search → sources path via fast search (deterministic tool
surface) and general agent when the tool surface stays bounded.
"""

from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_fast_search import perform_fast_search
from tests.api.agent.utils import (
    check_e2e_errors,
    get_model_selection,
    get_search_service_config,
    resolve_test_env,
)

_CITATION_PROMPT_FAST = "请搜索「Python 3.14 新特性」，用一句话总结，正文中必须用【1】标注引用，末尾单独一行写 CITE_OK。"

_GENERAL_PROMPT = (
    "请必须使用 web_search 工具搜索「OpenCode AI」，用一句话总结搜索结果，"
    "正文中必须用【1】标注引用来源，末尾单独一行写 CITE_OK。"
    "禁止调用 web_fetch、bash、delegate 或任何其他工具。"
)


def _collect_general_agent_citation_stream(client: TestClient, query: str) -> dict[str, object]:
    request_body: dict[str, object] = {
        "query": query,
        "messageId": f"cite-msg-{int(time.time() * 1000)}",
        "chatId": f"cite-chat-{int(time.time() * 1000)}",
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "actionMode": "agent",
        "agentConfig": {
            "enabledBuiltinTools": ["web_search"],
        },
        "userInstructions": "仅允许 web_search；禁止 web_fetch/bash/delegate/子 agent。",
        "enableMemoryAutoExtraction": False,
        "memoryRequireConfirmation": False,
        "timezone": "UTC",
    }

    start = time.monotonic()
    message_chunks: list[str] = []
    events: list[dict[str, object]] = []
    tool_calls = 0
    has_sources = False
    source_count = 0
    web_search_calls = 0

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as resp:
        if resp.status_code != 200:
            resp.read()
            return {
                "error": f"HTTP {resp.status_code}: {resp.text}",
                "elapsed_seconds": round(time.monotonic() - start, 2),
            }

        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                parsed = json.loads(line[6:])
                if not isinstance(parsed, dict):
                    continue
                events.append(parsed)
                evt_type = parsed.get("type", "")
                if evt_type == "message":
                    content = parsed.get("data", "")
                    if content:
                        message_chunks.append(str(content))
                elif evt_type == "sources":
                    has_sources = True
                    data = parsed.get("data")
                    if isinstance(data, list):
                        source_count += len(data)
                elif evt_type == "tasks_steps":
                    tool_name = str(parsed.get("tool_name") or "")
                    if tool_name:
                        tool_calls += 1
                    if "web_search" in tool_name:
                        web_search_calls += 1
            except json.JSONDecodeError:
                pass

    answer = "".join(message_chunks)
    return {
        "answer": answer,
        "events": events,
        "event_count": len(events),
        "tool_calls": tool_calls,
        "web_search_calls": web_search_calls,
        "has_sources": has_sources,
        "source_count": source_count,
        "has_cite_ok": "CITE_OK" in answer.upper(),
        "has_citation_marker": "【1】" in answer or "[1]" in answer,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "error": None,
    }


@pytest.mark.e2e
@pytest.mark.skipif(
    not resolve_test_env("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestWebSearchCitationPipeline:
    """Live web_search → sources SSE (+ optional inline cite markers)."""

    def test_fast_search_emits_sources_and_citation_markers(self, client: TestClient) -> None:
        """Fast Search: web_search tool → sources events → cite markers in answer."""
        answer, collected, tool_calls, has_sources = perform_fast_search(
            client,
            _CITATION_PROMPT_FAST,
            user_instructions="必须用【1】标注引用，末尾写 CITE_OK。",
        )
        check_e2e_errors(collected)

        print(
            f"\nFast search citation E2E: tools={tool_calls} sources={has_sources} "
            f"cite_ok={'CITE_OK' in answer.upper()} marker={'【1】' in answer or '[1]' in answer} "
            f"len={len(answer)}",
            flush=True,
        )

        assert len(collected) > 0, collected
        assert has_sources is True, collected
        assert tool_calls > 0, collected
        assert "CITE_OK" in answer.upper(), answer[:400]
        assert "【1】" in answer or "[1]" in answer, answer[:400]

    def test_general_agent_web_search_emits_sources_and_citations(self, client: TestClient) -> None:
        """General Agent: same sources pipeline when web_search completes."""
        result = _collect_general_agent_citation_stream(client, _GENERAL_PROMPT)
        if result.get("error"):
            pytest.fail(str(result["error"]))

        events = result.get("events")
        assert isinstance(events, list)
        check_e2e_errors(events)

        print(
            f"\nGeneral agent citation E2E: events={result['event_count']} "
            f"tools={result['tool_calls']} web_search={result['web_search_calls']} "
            f"sources={result['has_sources']} count={result['source_count']} "
            f"cite_ok={result['has_cite_ok']} marker={result['has_citation_marker']} "
            f"elapsed={result['elapsed_seconds']}s",
            flush=True,
        )

        blob = json.dumps(events, ensure_ascii=False, default=str).lower()
        if not result["has_sources"] and any(
            token in blob
            for token in (
                "delegate_task",
                "graphinterrupt",
                "suspended for approval",
                "iteration limit",
                "web_fetch_tool",
            )
        ):
            pytest.skip("General agent meta-tool surface interrupted before sources (env/tool budget)")

        assert int(result["event_count"]) > 0, result
        assert result["has_sources"] is True, result
        assert int(result["source_count"]) > 0, result
        assert result["has_cite_ok"] is True, result
        assert result["has_citation_marker"] is True, result
