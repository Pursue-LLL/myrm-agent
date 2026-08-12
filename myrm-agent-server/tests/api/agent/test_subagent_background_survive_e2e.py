"""wait=false 后台子代理在父 agent-stream 结束后仍运行（不被 cleanup_run 误取消）。

回归验证：父 agent run 正常结束时 ``cleanup_run`` 以 ``include_detached=False``
调用 ``cancel_all_children``，``wait=false`` 异步 spawn 的后台子代理必须继续运行，
与 SUB_AGENT_SYSTEM.md §19「wait=false 子 Agent 可在 parent gateway stream 结束后
继续运行」的设计目标一致。
"""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import build_approval_resume_value, get_model_selection

# 与 chrome_e2e 的 _DELEGATE_QUERY 保持一致的强提示模板：确保 LLM 走原生
# Function Calling 调用 delegate_task_tool，并显式传 timeout 覆盖
# bash_code_execute_tool 默认 60s 上限。
_DELEGATE_QUERY = (
    "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'test_bash'，wait 设为 false。"
    "子智能体的任务：调用 bash_code_execute_tool 执行命令 `sleep 120`，关键要求：run_in_background 必须为 false（前台运行），"
    "timeout 参数必须显式设为 180——bash_code_execute_tool 的默认超时只有 60 秒，若不显式传 timeout，"
    "sleep 120 会在 60 秒后被强制中断并直接失败；绝对禁止使用后台方式或 & 符号，"
    "必须等待命令完全执行完成后才能汇报结果并结束。"
    "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，"
    "绝对不要在文本中输出 XML 格式的工具调用！"
)

_BASH_WORKER_PRESET = {
    "system_prompt": "You are a bash execution worker.",
    "tools": ["bash_code_execute_tool"],
}


def _stream_collect(
    client: TestClient,
    request_data: dict[str, object],
    collected: list[dict[str, object]],
) -> None:
    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_data, timeout=180.0
    ) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                collected.append(json.loads(data_str))
            except json.JSONDecodeError:
                continue


def _stream_with_auto_approve(
    client: TestClient,
    request_data: dict[str, object],
) -> list[dict[str, object]]:
    """Consume the parent stream, auto-approving HITL requests like a real user."""
    collected: list[dict[str, object]] = []
    _stream_collect(client, request_data, collected)
    for _ in range(10):
        approval_required = any(
            d.get("type") in ("approval_required", "tool_approval_request")
            for d in reversed(collected)
        )
        if not approval_required:
            break
        resume_request = dict(request_data)
        resume_request["resumeValue"] = build_approval_resume_value()
        before = len(collected)
        _stream_collect(client, resume_request, collected)
    return collected


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_background_subagent_survives_parent_stream_end(client: TestClient) -> None:
    """父 agent-stream 流结束后，wait=false 后台子代理必须仍处于 running 状态。"""
    # conftest 的测试 app 未挂载 subagents router，此处补挂载以查询子代理列表。
    from app.api.agents import subagents

    client.app.include_router(subagents.router, prefix="/api/v1/chats", tags=["subagents"])

    chat_id = str(uuid.uuid4())
    request_payload: dict[str, object] = {
        "query": _DELEGATE_QUERY,
        "chatId": chat_id,
        "messageId": f"bg-survive-{uuid.uuid4().hex[:12]}",
        "modelSelection": get_model_selection(),
        "actionMode": "general",
        "ephemeral_subagents": {"test_bash": _BASH_WORKER_PRESET},
    }

    # 完整消费父流（模拟真实用户等待完整回复并批准 HITL），父 run 正常结束时 cleanup_run 执行。
    collected = _stream_with_auto_approve(client, request_payload)
    completion_blocked = any(
        d.get("type") in ("approval_required", "tool_approval_request")
        for d in collected[-20:]
    )
    if completion_blocked:
        pytest.fail(f"Agent stream still pending HITL after auto-approve: {collected[-5:]!r}")

    # 父流结束后立即查询子代理列表：bash_worker 必须仍 running。
    deadline = time.monotonic() + 30.0
    running_rows: list[dict[str, object]] = []
    last_payload: object = None
    while time.monotonic() < deadline:
        list_resp = client.get(f"/api/v1/chats/{chat_id}/subagents")
        payload = list_resp.json()
        last_payload = payload
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            running_rows = [
                row for row in data if isinstance(row, dict) and row.get("status") == "running"
            ]
            if running_rows:
                break
        time.sleep(2.0)

    assert running_rows, (
        "后台子代理在父 agent-stream 结束后被取消（cleanup_run 误 cancel wait=false 子代理）。"
        f"subagents={last_payload!r}"
    )

    # 清理：取消所有后台子代理，避免残留进程。
    for row in running_rows:
        task_id = row.get("task_id")
        if isinstance(task_id, str) and task_id:
            client.post(f"/api/v1/chats/{chat_id}/subagents/{task_id}/cancel")
