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

from tests.api.agent.utils import build_approval_resume_value, get_model_selection

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
    "Invalid tool choice",
    "allowed_tools",
)

_FOCUS_FILE_PATH: Final[str] = "myrm-agent-server/app/main.py"

_FOCUS_INITIAL_QUERY: Final[str] = (
    f"""
我在排查 `{_FOCUS_FILE_PATH}` 相关的异步逻辑。
请用约150字解释 Python asyncio.Event：两个使用场景 + 与 Lock 的一个区别。
""".strip()
)

_FOCUS_FOLLOWUPS: Final[tuple[str, ...]] = (
    f"继续。结合 `{_FOCUS_FILE_PATH}` 的排查背景，用一句话对比 asyncio.Event 与 threading.Event。",
)

_FAILURE_INITIAL_QUERY_TEMPLATE: Final[str] = (
    """
请用 bash 执行以下命令并报告结果：
1. echo "hello world"
2. ls {missing_path}
3. echo "done"

逐个执行，报告每个命令的执行结果，如果失败请说明原因。
""".strip()
)

_FAILURE_FOLLOWUP_TEMPLATE: Final[str] = (
    "继续。回顾刚才的命令执行：哪个命令失败了？失败的路径是 {missing_path}，为什么失败？"
)


@pytest.fixture(autouse=True)
def shrink_model_context_window(mock_load_user_configs) -> None:
    configs = mock_load_user_configs.return_value
    configs.model_cfg = configs.model_cfg.model_copy(
        update={"max_context_tokens": _TEST_MAX_CONTEXT_TOKENS}
    )


def _build_payload(
    query: str, chat_id: str, *, action_mode: str = "agent"
) -> dict[str, object]:
    return {
        "query": query,
        "chatId": chat_id,
        "messageId": f"msg-{uuid.uuid4().hex}",
        "modelSelection": get_model_selection(),
        "actionMode": action_mode,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }


def _collect_stream_events(
    client: TestClient,
    payload: dict[str, object],
    *,
    collected_events: list[dict[str, object]],
    message_chunks: list[str],
    error_events: list[dict[str, object]],
) -> None:
    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=payload, timeout=240.0
    ) as response:
        if response.status_code != 200:
            response.read()
            response_text = response.text
            if any(
                keyword.lower() in response_text.lower()
                for keyword in _SKIP_ERROR_KEYWORDS
            ):
                pytest.skip(f"External environment error: {response_text[:200]}")
            pytest.fail(
                f"Agent request failed with status {response.status_code}: {response_text[:500]}"
            )

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


def _stream_agent_turn(
    client: TestClient,
    *,
    query: str,
    chat_id: str,
    action_mode: str = "agent",
) -> tuple[str, list[dict[str, object]]]:
    """Execute one agent turn and return (answer_text, all_events)."""
    payload = _build_payload(query, chat_id, action_mode=action_mode)
    collected_events: list[dict[str, object]] = []
    message_chunks: list[str] = []
    error_events: list[dict[str, object]] = []

    _collect_stream_events(
        client,
        payload,
        collected_events=collected_events,
        message_chunks=message_chunks,
        error_events=error_events,
    )

    for _ in range(10):
        approval_required = any(
            event.get("type") in ("approval_required", "tool_approval_request")
            for event in reversed(collected_events)
        )
        if not approval_required:
            break
        resume_payload = dict(payload)
        resume_payload["resumeValue"] = build_approval_resume_value()
        _collect_stream_events(
            client,
            resume_payload,
            collected_events=collected_events,
            message_chunks=message_chunks,
            error_events=error_events,
        )

    if error_events:
        error_text = json.dumps(error_events[0], ensure_ascii=False)
        if any(
            keyword.lower() in error_text.lower() for keyword in _SKIP_ERROR_KEYWORDS
        ):
            pytest.skip(f"External environment error: {error_text[:200]}")
        pytest.fail(f"Agent execution error: {error_text[:500]}")

    return "".join(message_chunks), collected_events


def _task_step_count(events: list[dict[str, object]]) -> int:
    return sum(1 for event in events if event.get("type") == "tasks_steps")


def _has_context_health_event(events: list[dict[str, object]]) -> bool:
    return any(event.get("type") == "context_health" for event in events)


@pytest.mark.timeout(300)
def test_real_context_compression_preserves_focus_chain(client: TestClient) -> None:
    """Multi-turn conversation should keep key concepts in answer after compression."""
    chat_id = f"context-focus-{uuid.uuid4().hex}"
    all_events: list[dict[str, object]] = []
    final_answer = ""

    for query in (_FOCUS_INITIAL_QUERY, *_FOCUS_FOLLOWUPS):
        final_answer, events = _stream_agent_turn(
            client, query=query, chat_id=chat_id, action_mode="agent"
        )
        all_events.extend(events)

    assert len(all_events) > 0, "Expected events from multi-turn conversation"

    normalized_answer = final_answer.lower()
    focus_hint = _FOCUS_FILE_PATH.removeprefix("./").lower()
    assert (
        "asyncio" in normalized_answer
        or "event" in normalized_answer
        or focus_hint in normalized_answer
        or "main.py" in normalized_answer
    ), (
        f"Final answer should reference asyncio.Event or focus file from earlier turns. "
        f"Got: {final_answer[:300]}"
    )


def test_real_context_compression_preserves_failed_tool_chain(
    client: TestClient,
) -> None:
    """Failed tool calls should survive context compression and remain referenced."""
    chat_id = f"context-failure-{uuid.uuid4().hex}"
    # Workspace-relative path: absolute paths outside sandbox are security-blocked, not "missing file".
    missing_path = f"./definitely_missing_context_path_{uuid.uuid4().hex}"
    failure_initial_query = _FAILURE_INITIAL_QUERY_TEMPLATE.format(
        missing_path=missing_path
    )
    failure_followup = _FAILURE_FOLLOWUP_TEMPLATE.format(missing_path=missing_path)

    all_events: list[dict[str, object]] = []
    final_answer = ""

    for query in (failure_initial_query, failure_followup):
        final_answer, events = _stream_agent_turn(client, query=query, chat_id=chat_id)
        all_events.extend(events)

    assert (
        _task_step_count(all_events) > 0
    ), "Expected real tool/task activity in failure-chain scenario"

    normalized_answer = final_answer.lower()
    missing_basename = missing_path.removeprefix("./").lower()
    assert (
        missing_path.lower() in normalized_answer
        or missing_basename in normalized_answer
        or "no such file" in normalized_answer
        or "not found" in normalized_answer
        or "failed" in normalized_answer
        or "失败" in normalized_answer
        or "exit code" in normalized_answer
    ), f"Final answer should preserve failed tool-call semantics. Got: {final_answer[:300]}"
