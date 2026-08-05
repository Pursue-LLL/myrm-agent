"""SSE stream collection and resume loop for MCP Agent E2E tests."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.mcp_e2e_helpers import (
    ENV_ERROR_KEYWORDS,
    MAX_TOOL_STUCK_APPROVALS,
    STREAM_TIMEOUT,
    TEST_WALL_CLOCK_LIMIT,
)


def print_tasks_steps_payload(tool_name: str, step_data_list: object) -> None:
    """Print tool input payloads from a tasks_steps event (pytest -s live stream)."""
    if not isinstance(step_data_list, list):
        return
    for idx, item in enumerate(step_data_list):
        if not isinstance(item, dict):
            continue
        if tool_name == "file_read_tool":
            print(f"   [{idx}] file_path={item.get('file_path')}")
        elif tool_name == "bash_code_execute_tool":
            code = str(item.get("code", ""))
            preview = code if len(code) <= 3000 else code[:3000] + "\n   ... [truncated]"
            print(f"   [{idx}] code ({len(code)} chars):\n{preview}")
        elif tool_name == "skill_select_tool":
            print(f"   [{idx}] skill_name={item.get('skill_name')}")
        else:
            print(f"   [{idx}] {json.dumps(item, ensure_ascii=False)[:500]}")


def has_final_answer(collected_data: list[dict[str, object]]) -> bool:
    """True when message+message_end exist and no tool approval is still pending."""
    if not any(d.get("type") == "message" for d in collected_data):
        return False
    if not any(d.get("type") == "message_end" for d in collected_data):
        return False

    last_approval_idx = -1
    for i, event in enumerate(collected_data):
        if event.get("type") in ("approval_required", "tool_approval_request"):
            last_approval_idx = i

    if last_approval_idx < 0:
        return True

    post_approval = collected_data[last_approval_idx + 1 :]
    return any(
        event.get("type") == "tasks_steps" and event.get("status") == "success"
        for event in post_approval
    )


@dataclass
class McpStreamRunResult:
    collected_data: list[dict[str, object]]
    message_chunks: list[str]
    tool_results: list[str]
    tool_stuck_count: int
    line_count: int
    full_answer: str
    error_events: list[dict[str, object]]
    event_types: list[str]


def run_mcp_agent_stream(
    client: TestClient,
    search_request: dict[str, object],
    *,
    resume_on_iteration_limit: bool,
    log: Callable[[str], None],
) -> McpStreamRunResult:
    """Stream agent MCP E2E events; optionally auto-resume on iteration_limit_reached."""
    collected_data: list[dict[str, object]] = []
    message_chunks: list[str] = []
    tool_results: list[str] = []
    current_message_line = ""
    is_first_message = True
    last_sources_count = 0
    reasoning_count = 0
    tool_stuck_count = 0
    line_count = 0

    test_chat_id = str(search_request["chatId"])
    headers = {"X-Chat-ID": test_chat_id}
    start_time = time.time()

    def _process_event(data: dict[str, object]) -> None:
        nonlocal current_message_line, is_first_message, last_sources_count, reasoning_count, tool_stuck_count
        data_type = data.get("type", "unknown")

        if data_type == "message":
            content = data.get("data", "")
            if content:
                message_chunks.append(str(content))
                if is_first_message:
                    print("\n💬 AI 回复: ", end="", flush=True)
                    is_first_message = False
                if "\n" in content:
                    parts = str(content).split("\n")
                    for i, part in enumerate(parts):
                        print(part, end="", flush=True)
                        if i < len(parts) - 1:
                            print()
                else:
                    print(content, end="", flush=True)
        elif data_type == "reasoning":
            reasoning_count += 1
            if reasoning_count % 20 == 1:
                print(".", end="", flush=True)
        elif data_type == "sources":
            if current_message_line:
                print()
                current_message_line = ""
            sources_data = data.get("data", [])
            tool_results.append(str(sources_data))
            if len(sources_data) != last_sources_count:
                print(f"\n🔍 搜索来源: {len(sources_data)} 个结果")
                last_sources_count = len(sources_data)
        elif data_type == "tasks_steps":
            if current_message_line:
                print()
                current_message_line = ""
            tool_name = data.get("tool_name", "unknown")
            status = data.get("status", "success")
            step_data_list = data.get("data", [])
            status_icon = "❌" if status == "error" else "🔧"
            print(f"\n{status_icon} 工具调用: {tool_name}")
            if step_data_list:
                print(f"   步骤数据: {len(step_data_list)} 项")
                print_tasks_steps_payload(str(tool_name), step_data_list)
        elif data_type == "progress":
            status = data.get("data", {})
            pct = status.get("progress_pct", "") if isinstance(status, dict) else ""
            print(f"\n📊 进度: {pct}%", flush=True)
        elif data_type == "tools_snapshot":
            tools_data = data.get("data", [])
            count = len(tools_data) if isinstance(tools_data, list) else 0
            print(f"\n🛠️ Agent 已就绪 ({count} 工具加载完成)", flush=True)
        elif data_type == "tool_start":
            print("\n⏳ 工具启动中...", flush=True)
        elif data_type == "tool_heartbeat":
            print("♥", end="", flush=True)
        elif data_type in ("approval_required", "tool_approval_request"):
            approval_data = data.get("data", data)
            action_type = ""
            if isinstance(approval_data, dict):
                action_type = approval_data.get("action_type", "")
            if action_type == "tool_stuck":
                tool_stuck_count += 1
                log(f"Tool stuck detected (count={tool_stuck_count})")
        elif data_type == "error":
            if current_message_line:
                print()
                current_message_line = ""
            print(f"\n❌ 错误: {data}")

    def _stream_request(req_data: dict[str, object]) -> int:
        nonlocal line_count
        elapsed_total = time.time() - start_time
        if elapsed_total > TEST_WALL_CLOCK_LIMIT:
            log(f"Wall-clock limit reached ({elapsed_total:.0f}s > {TEST_WALL_CLOCK_LIMIT}s), skipping stream")
            return 0

        with client.stream("POST", "/api/v1/agents/agent-stream", json=req_data, headers=headers) as response:
            log(f"收到响应: {response.status_code}")
            if response.status_code != 200:
                response.read()
                print(f"\nHTTP错误 {response.status_code}:")
                print(f"响应内容: {response.text}")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")

            log("开始读取流式响应...\n")
            round_lines = 0
            stream_start = time.time()
            for line in response.iter_lines():
                round_lines += 1
                line_count += 1

                now = time.time()
                if now - stream_start > STREAM_TIMEOUT:
                    log(f"Stream timeout after {STREAM_TIMEOUT}s, breaking")
                    break
                if now - start_time > TEST_WALL_CLOCK_LIMIT:
                    log(f"Wall-clock limit reached ({now - start_time:.0f}s), breaking stream")
                    break

                if not line:
                    continue
                line_text = line.strip() if isinstance(line, str) else line.decode().strip()
                if not line_text.startswith("data: "):
                    continue
                try:
                    data = json.loads(line_text[6:])
                    if data is None:
                        continue
                    collected_data.append(data)
                    _process_event(data)
                except json.JSONDecodeError as exc:
                    log(f"JSON解析错误: {exc}")
            return round_lines

    log("📡 发送 POST 请求...")
    _stream_request(search_request)

    for round_idx in range(10):
        if has_final_answer(collected_data):
            log("已收到完整回答，停止后续 resume")
            break

        if time.time() - start_time > TEST_WALL_CLOCK_LIMIT:
            log("Wall-clock limit reached, stopping resume loop")
            break

        needs_resume = False
        resume_reason = ""
        is_tool_stuck = False
        for data in reversed(collected_data):
            event_type = data.get("type")
            if event_type in ("approval_required", "tool_approval_request"):
                approval_data = data.get("data", data)
                if isinstance(approval_data, dict) and approval_data.get("action_type") == "tool_stuck":
                    is_tool_stuck = True
                needs_resume = True
                resume_reason = "approval"
                break
            if event_type == "iteration_limit_reached":
                if resume_on_iteration_limit:
                    needs_resume = True
                    resume_reason = "iteration_limit"
                else:
                    log("Iteration limit reached; resume disabled for this test — stopping")
                break
            if event_type == "message":
                break

        if not needs_resume:
            break

        if is_tool_stuck and tool_stuck_count > MAX_TOOL_STUCK_APPROVALS:
            log(f"Tool stuck {tool_stuck_count} times (limit={MAX_TOOL_STUCK_APPROVALS}), stopping resume")
            break

        resume_request = search_request.copy()
        resume_request["messageId"] = str(uuid.uuid4())

        if resume_reason == "approval":
            log(f"Auto-approving tool call (round {round_idx + 1})...")
            resume_request["resumeValue"] = {
                "decisions": [
                    {
                        "type": "approve",
                        "extensions": {"allowAlways": True},
                    }
                ],
            }
        else:
            log(f"Iteration limit reached, resuming (round {round_idx + 1})...")
            resume_request["resumeValue"] = {"resume": True}

        _stream_request(resume_request)

    if message_chunks:
        print()

    total_elapsed = time.time() - start_time
    log(f"\nStream finished: {line_count} lines, {len(collected_data)} events, {total_elapsed:.1f}s total")

    error_events = [d for d in collected_data if d.get("type") == "error"]
    event_types = [str(d.get("type", "unknown")) for d in collected_data]

    return McpStreamRunResult(
        collected_data=collected_data,
        message_chunks=message_chunks,
        tool_results=tool_results,
        tool_stuck_count=tool_stuck_count,
        line_count=line_count,
        full_answer="".join(message_chunks),
        error_events=error_events,
        event_types=event_types,
    )


def skip_on_environment_errors(result: McpStreamRunResult) -> None:
    """Skip test when LLM/network errors are detected in the stream."""
    if len(result.collected_data) == 0:
        pytest.skip("No events received (LLM / network issue)")

    if result.error_events:
        error_msg = str(result.error_events[0].get("error", ""))
        if any(kw in error_msg for kw in ENV_ERROR_KEYWORDS):
            pytest.skip(f"Environment issue: {error_msg[:120]}")


def print_event_sequence(event_types: list[str]) -> None:
    compressed_events: list[str] = []
    for evt in event_types:
        if evt == "message":
            if not compressed_events or compressed_events[-1] != "message":
                compressed_events.append("message")
        else:
            compressed_events.append(evt)

    print(f"\nEvent sequence: {' -> '.join(compressed_events)}")
    print(f"(raw: {len(event_types)}, compressed: {len(compressed_events)})")
