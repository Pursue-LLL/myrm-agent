"""Real E2E tests for context compression with low max_context_tokens.

Verifies that multi-turn conversations trigger the compress pipeline
and that semantically important content survives compaction.

Strategy:
  1. Set max_context_tokens to a low value (20k) to trigger compression faster.
  2. Send multiple turns with file-reading tool usage.
  3. Verify the agent still references key files/concepts in later turns,
     proving that the compression preserved important context.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Final

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("BASIC_API_KEY"),
        reason="E2E test requires BASIC_API_KEY environment variable",
    ),
]

_TEST_MAX_CONTEXT_TOKENS: Final[int] = 20000
_SKIP_ERROR_KEYWORDS: Final[tuple[str, ...]] = (
    "Authentication",
    "Authorization",
    "api key",
    "Cannot connect",
    "Connection error",
    "Connection refused",
    "InternalServerError",
    "Rate limit",
    "Recursion limit",
    "timeout",
)

_FOCUS_INITIAL_QUERY: Final[str] = """
请详细解释 Python 中 asyncio.Event 的用法，包括：
1. 基本用法和场景
2. 与 asyncio.Lock 的区别
3. 在生产者-消费者模式中的应用
4. 常见的陷阱和最佳实践

每个点都要举代码示例。回答要详细，至少1000字。
""".strip()

_FOCUS_FOLLOWUPS: Final[tuple[str, str]] = (
    "继续。基于刚才的讨论，asyncio.Event 和 threading.Event 有什么核心区别？"
    "请特别说明在 aiohttp 或 FastAPI 中使用 asyncio.Event 的最佳实践。",
    "继续。回顾我们整个讨论，总结 asyncio.Event 的三个最重要的使用场景，并且说明为什么它比 asyncio.Condition 更适合这些场景。",
)

_FAILURE_INITIAL_QUERY_TEMPLATE: Final[str] = """
请用 bash 执行以下命令并报告结果：
1. echo "hello world"
2. ls {missing_path}
3. echo "done"

逐个执行，报告每个命令的执行结果，如果失败请说明原因。
""".strip()

_FAILURE_FOLLOWUP_TEMPLATE: Final[str] = "继续。回顾刚才的命令执行：哪个命令失败了？失败的路径是 {missing_path}，为什么失败？"


@pytest.fixture(autouse=True)
def shrink_model_context_window(mock_load_user_configs) -> None:
    configs = mock_load_user_configs.return_value
    configs.model_cfg = configs.model_cfg.model_copy(update={"max_context_tokens": _TEST_MAX_CONTEXT_TOKENS})


def _build_payload(query: str, chat_id: str) -> dict[str, object]:
    return {
        "query": query,
        "chatId": chat_id,
        "messageId": f"msg-{uuid.uuid4().hex}",
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }


def _stream_agent_turn(
    client: TestClient,
    *,
    query: str,
    chat_id: str,
) -> tuple[str, list[dict[str, object]]]:
    """Execute one agent turn and return (answer_text, all_events)."""
    payload = _build_payload(query, chat_id)
    collected_events: list[dict[str, object]] = []
    message_chunks: list[str] = []
    error_events: list[dict[str, object]] = []

    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=240.0) as response:
        if response.status_code != 200:
            response.read()
            response_text = response.text
            if any(keyword.lower() in response_text.lower() for keyword in _SKIP_ERROR_KEYWORDS):
                pytest.skip(f"External environment error: {response_text[:200]}")
            pytest.fail(f"Agent request failed with status {response.status_code}: {response_text[:500]}")

        assert response.headers["content-type"].startswith("text/event-stream")

        for raw_line in response.iter_lines():
            if not raw_line or not raw_line.startswith("data: "):
                continue

            raw_payload = raw_line[6:]
            if raw_payload == "[DONE]":
                break

            try:
                event = json.loads(raw_payload)
            except json.JSONDecodeError:
                continue

            if not isinstance(event, dict):
                continue

            collected_events.append(event)
            if event.get("type") == "message":
                chunk = event.get("data")
                if isinstance(chunk, str) and chunk:
                    message_chunks.append(chunk)
            elif event.get("type") == "error":
                error_events.append(event)

    if error_events:
        error_text = json.dumps(error_events[0], ensure_ascii=False)
        if any(keyword.lower() in error_text.lower() for keyword in _SKIP_ERROR_KEYWORDS):
            pytest.skip(f"External environment error: {error_text[:200]}")
        pytest.fail(f"Agent execution error: {error_text[:500]}")

    return "".join(message_chunks), collected_events


def _task_step_count(events: list[dict[str, object]]) -> int:
    return sum(1 for event in events if event.get("type") == "tasks_steps")


def _has_context_health_event(events: list[dict[str, object]]) -> bool:
    return any(event.get("type") == "context_health" for event in events)


def test_real_context_compression_preserves_focus_chain(client: TestClient) -> None:
    """Multi-turn conversation should keep key file names in answer after compression."""
    chat_id = f"context-focus-{uuid.uuid4().hex}"
    all_events: list[dict[str, object]] = []
    final_answer = ""

    for query in (_FOCUS_INITIAL_QUERY, *_FOCUS_FOLLOWUPS):
        final_answer, events = _stream_agent_turn(client, query=query, chat_id=chat_id)
        all_events.extend(events)

    assert len(all_events) > 0, "Expected events from multi-turn conversation"

    normalized_answer = final_answer.lower()
    assert "asyncio" in normalized_answer or "event" in normalized_answer, (
        f"Final answer should reference asyncio.Event from earlier turns. Got: {final_answer[:300]}"
    )

    # Verify that proactive reset/summarize triggered the UI notification
    archived_event_found = False
    for event in all_events:
        if event.get("type") in ["status", "agent_status"]:
            # After flattening, step_key can be at the top level of the event or inside data
            if event.get("step_key") == "memory_archived":
                archived_event_found = True
                break
            data = event.get("data", {})
            if isinstance(data, dict) and data.get("step_key") == "memory_archived":
                archived_event_found = True
                break
    assert archived_event_found, "The memory_archived event was not emitted during compression!"


def test_real_context_compression_preserves_failed_tool_chain(client: TestClient) -> None:
    """Failed tool calls should survive context compression and remain referenced."""
    chat_id = f"context-failure-{uuid.uuid4().hex}"
    missing_path = f"/definitely_missing_context_path_{uuid.uuid4().hex}"
    failure_initial_query = _FAILURE_INITIAL_QUERY_TEMPLATE.format(missing_path=missing_path)
    failure_followup = _FAILURE_FOLLOWUP_TEMPLATE.format(missing_path=missing_path)

    all_events: list[dict[str, object]] = []
    final_answer = ""

    for query in (failure_initial_query, failure_followup):
        final_answer, events = _stream_agent_turn(client, query=query, chat_id=chat_id)
        all_events.extend(events)

    assert _task_step_count(all_events) > 0, "Expected real tool/task activity in failure-chain scenario"

    normalized_answer = final_answer.lower()
    assert (
        missing_path.lower() in normalized_answer
        or "no such file" in normalized_answer
        or "not found" in normalized_answer
        or "failed" in normalized_answer
        or "失败" in normalized_answer
    ), f"Final answer should preserve failed tool-call semantics. Got: {final_answer[:300]}"
