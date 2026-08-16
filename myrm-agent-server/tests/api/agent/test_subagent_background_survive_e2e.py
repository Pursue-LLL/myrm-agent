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
def _delegate_query(sleep_sec: int, timeout_sec: int = 180, *, await_child: bool = True) -> str:
    base = (
        "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'test_bash'，wait 设为 false。"
        "子智能体的任务：调用 bash_code_execute_tool 执行命令 "
        f"`sleep {sleep_sec}`，关键要求：run_in_background 必须为 false（前台运行），"
        f"timeout 参数必须显式设为 {timeout_sec}——bash_code_execute_tool 的默认超时只有 60 秒，若不显式传 timeout，"
        f"sleep {sleep_sec} 会在 60 秒后被强制中断并直接失败；绝对禁止使用后台方式或 & 符号，"
        "必须等待命令完全执行完成后才能汇报结果并结束。"
        "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，"
        "绝对不要在文本中输出 XML 格式的工具调用！"
    )
    if not await_child:
        base += (
            "另外：你只需创建该子智能体并立即结束当前任务即可，绝不要轮询、等待子智能体完成，"
            "也不要调用 subagent_control_tool。子智能体会在后台继续运行，其结果稍后可见。"
        )
    return base


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
        raced_busy = any(
            d.get("type") == "error" and "busy" in str(d.get("data", "")).lower()
            for d in collected[before:]
        )
        if raced_busy:
            # Resume raced the previous agent turn's async teardown while the
            # session lock was still held; retry after it releases instead of
            # surfacing a spurious AgentBusyError.
            time.sleep(1.0)
            del collected[before:]
            _stream_collect(client, resume_request, collected)
    return collected


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_background_subagent_survives_parent_stream_end(client: TestClient) -> None:
    """父 agent-stream 流结束后，wait=false 后台子代理必须仍处于 running 状态。"""
    # conftest 的测试 app 未挂载 subagents router，此处补挂载以查询子代理列表。
    from app.api.agents import subagents

    client.app.include_router(
        subagents.router, prefix="/api/v1/chats", tags=["subagents"]
    )

    chat_id = str(uuid.uuid4())
    request_payload: dict[str, object] = {
        "query": _delegate_query(120, await_child=False),
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
        pytest.fail(
            f"Agent stream still pending HITL after auto-approve: {collected[-5:]!r}"
        )

    # 父流结束后立即查询子代理列表：bash_worker 必须仍存活（running 或 completed）。
    # wait=false 语义是「不被 cleanup_run 取消」——completed 也是存活证据；绝对不允许 failed/cancelled。
    deadline = time.monotonic() + 30.0
    alive_rows: list[dict[str, object]] = []
    last_payload: object = None
    while time.monotonic() < deadline:
        list_resp = client.get(f"/api/v1/chats/{chat_id}/subagents")
        payload = list_resp.json()
        last_payload = payload
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            alive_rows = [
                row
                for row in data
                if isinstance(row, dict) and row.get("status") in ("running", "completed")
            ]
            if alive_rows:
                break
        time.sleep(2.0)

    assert alive_rows, (
        "后台子代理在父 agent-stream 结束后被取消（cleanup_run 误 cancel wait=false 子代理）。"
        f"subagents={last_payload!r}"
    )

    # 清理：取消所有后台子代理，避免残留进程。
    for row in alive_rows:
        task_id = row.get("task_id")
        if isinstance(task_id, str) and task_id:
            client.post(f"/api/v1/chats/{chat_id}/subagents/{task_id}/cancel")


def _mount_subagents_router(client: TestClient) -> None:
    from app.api.agents import subagents

    client.app.include_router(
        subagents.router, prefix="/api/v1/chats", tags=["subagents"]
    )


def _run_background_delegate(
    client: TestClient, chat_id: str, sleep_sec: int, timeout_sec: int
) -> list[dict[str, object]]:
    request_payload: dict[str, object] = {
        "query": _delegate_query(sleep_sec, timeout_sec),
        "chatId": chat_id,
        "messageId": f"bg-{uuid.uuid4().hex[:12]}",
        "modelSelection": get_model_selection(),
        "actionMode": "general",
        "ephemeral_subagents": {"test_bash": _BASH_WORKER_PRESET},
    }
    return _stream_with_auto_approve(client, request_payload)


def _wait_running_subagents(
    client: TestClient, chat_id: str, timeout_sec: float = 60.0
) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout_sec
    running_rows: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/chats/{chat_id}/subagents").json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            running_rows = [
                row
                for row in data
                if isinstance(row, dict) and row.get("status") == "running"
            ]
            if running_rows:
                return running_rows
        time.sleep(2.0)
    return running_rows


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_background_subagent_cancelled_by_cancel_all_after_parent_stream_end(
    client: TestClient,
) -> None:
    """父流结束后 wait=false 后台子代理仍 running，且 cancel-all 可将其取消。

    验证 include_detached 语义的取消分支：父 run 正常结束保留后台子代理后，
    用户显式 cancel-all（registry 路径）必须能取消它。
    """
    _mount_subagents_router(client)
    chat_id = str(uuid.uuid4())
    _run_background_delegate(client, chat_id, sleep_sec=120, timeout_sec=180)

    running_rows = _wait_running_subagents(client, chat_id)
    assert (
        running_rows
    ), "父流结束后台子代理未 running（cleanup_run 误取消或 cancel-all 前置断言失败）。"
    task_id = str(running_rows[0].get("task_id") or "")
    assert task_id

    cancel_resp = client.post(f"/api/v1/chats/{chat_id}/subagents/cancel-all")
    assert cancel_resp.status_code == 200, cancel_resp.text
    payload = cancel_resp.json()
    assert payload.get("data", {}).get("cancelled", 0) >= 1, payload

    # GRACEFUL cancel：子代理在下一轮 LLM 检测 cancel flag 后退出，轮询等待终态。
    deadline = time.monotonic() + 90.0
    terminal_seen = False
    last_payload: object = None
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/chats/{chat_id}/subagents")
        list_payload = resp.json()
        last_payload = list_payload
        data = list_payload.get("data") if isinstance(list_payload, dict) else None
        if isinstance(data, list):
            row = next(
                (
                    r
                    for r in data
                    if isinstance(r, dict) and r.get("task_id") == task_id
                ),
                None,
            )
            if row is None:
                terminal_seen = True  # 已从 registry 消失
                break
            if row.get("status") in ("cancelled", "completed", "failed"):
                terminal_seen = True
                break
        time.sleep(2.0)

    assert (
        terminal_seen
    ), f"cancel-all 后后台子代理 {task_id} 未进入终态/消失: {last_payload!r}"


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_background_subagent_completed_observable_after_parent_stream_end(
    client: TestClient,
) -> None:
    """父流结束后台子代理完成后，REST 列表仍可观测 completed（COMPLETED_SUBAGENT_RESULTS）。"""
    _mount_subagents_router(client)
    chat_id = str(uuid.uuid4())
    _run_background_delegate(client, chat_id, sleep_sec=60, timeout_sec=90)

    running_rows = _wait_running_subagents(client, chat_id)
    assert running_rows, "父流结束后台子代理未 running"
    task_id = str(running_rows[0].get("task_id") or "")
    assert task_id

    deadline = time.monotonic() + 90.0
    completed_seen = False
    last_payload: object = None
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/chats/{chat_id}/subagents").json()
        last_payload = payload
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            row = next(
                (
                    r
                    for r in data
                    if isinstance(r, dict) and r.get("task_id") == task_id
                ),
                None,
            )
            if row and row.get("status") == "completed":
                completed_seen = True
                break
        time.sleep(2.0)

    assert (
        completed_seen
    ), f"后台子代理 {task_id} 完成后未在 REST 列表观测到 completed: {last_payload!r}"
