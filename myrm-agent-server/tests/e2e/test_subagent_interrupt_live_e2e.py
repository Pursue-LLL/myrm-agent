"""Live HTTP E2E: subagent high-risk bash approval interrupt → approve/allow-always/edit/reject.

Replaces the in-process ``TestClient`` variant (``tests/api/agent/test_subagent_interrupt_e2e.py``)
whose approval events cannot bridge the subagent -> parent stream in a single-process
TestClient. This version talks to the real SHPOIB agent-stream over HTTP, where the
approval middleware + ``ApprovalRegistry`` are fully wired.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_subagent_interrupt_live_e2e.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Callable, Iterator

import httpx
import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    ensure_e2e_hitl_mode,
    ensure_e2e_onboarding_complete,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)

from tests.support.e2e_runtime_guard import heartbeat_once  # noqa: E402
from tests.support.hitl_live_e2e import pin_and_verify_hitl_mode  # noqa: E402
from tests.support.subagent_hitl_stream import (  # noqa: E402
    run_interrupt_flow,
)

_DELEGATE_QUERY_TMPL = (
    "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'test_bash'，"
    "并且必须将 wait 参数设置为 true（同步等待子任务完成，不要异步）。"
    "子智能体必须调用 bash_code_execute_tool 工具实际执行这条命令（一字不改，禁止替换路径、"
    "禁止输出占位符、禁止只用文本描述而不调用工具）：`rm -rf {target_dir}`。"
    "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，"
    "绝对不要在文本中输出 XML 格式的工具调用！"
)

_SUBAGENT_SYSTEM_PROMPT = (
    "You are a bash execution worker. When given a shell command, "
    "you MUST call the bash_code_execute_tool tool with the exact command "
    "as-is (never replace paths or emit placeholders), then report the output."
)

_AGENT_SYSTEM_PROMPT = (
    "You are a helpful agent. When the user asks you to delegate a bash task to a subagent, "
    "use delegate_task_tool with agent_type='test_bash' and wait=true. "
    "The subagent has only bash_code_execute_tool. Report the subagent's result when it finishes."
)

_EPHEMERAL_SUBAGENTS: dict[str, dict[str, object]] = {
    "test_bash": {
        "system_prompt": _SUBAGENT_SYSTEM_PROMPT,
        "tools": ["bash_code_execute_tool"],
    }
}


def _create_delegating_agent(client: httpx.Client, api_base: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Subagent Interrupt LIVE {suffix}",
        "description": "Chrome LIVE HTTP E2E for subagent bash HITL",
        "system_prompt": _AGENT_SYSTEM_PROMPT,
        "skill_ids": [],
        "mcp_ids": [],
        "security_overrides": {"yoloModeEnabled": False, "autoModeEnabled": False},
    }
    resp = client.post(f"{api_base.rstrip('/')}/api/v1/user-agents", json=payload)
    resp.raise_for_status()
    body = resp.json()
    agent_id = (
        body.get("data", {}).get("id")
        if isinstance(body.get("data"), dict)
        else body.get("id")
    )
    if not isinstance(agent_id, str) or not agent_id:
        raise AssertionError(f"Failed to create delegating agent: {body!r}")
    return agent_id


def _seed_chat(
    client: httpx.Client,
    api_base: str,
    *,
    agent_id: str,
    chat_id: str,
) -> None:
    resp = client.post(
        f"{api_base.rstrip('/')}/api/v1/chats/",
        json={
            "chat_id": chat_id,
            "agent_id": agent_id,
            "action_mode": "general",
            "ephemeral_subagents": _EPHEMERAL_SUBAGENTS,
            "messages": [],
        },
    )
    resp.raise_for_status()


def _extract_subagent_tool_args(events: list[dict[str, object]]) -> dict[str, object]:
    approval_types = frozenset({"approval_required", "tool_approval_request"})
    for event in events:
        if event.get("type") not in approval_types:
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = data
        tool_calls = payload.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue
        first = tool_calls[0]
        if not isinstance(first, dict):
            continue
        raw_args = first.get("args")
        return dict(raw_args) if isinstance(raw_args, dict) else {}
    return {}


def _run_interrupt_case(
    client: httpx.Client,
    api_base: str,
    chat_id: str,
    target_dir: str,
    agent_id: str,
    *,
    resume_decision_factory: Callable[
        [list[dict[str, object]]], list[dict[str, object]]
    ],
) -> None:
    pin_and_verify_hitl_mode(api_base)
    _seed_chat(client, api_base, agent_id=agent_id, chat_id=chat_id)
    query = _DELEGATE_QUERY_TMPL.format(target_dir=target_dir)
    run_interrupt_flow(
        client,
        api_base,
        chat_id,
        agent_id,
        query,
        ephemeral_subagents=_EPHEMERAL_SUBAGENTS,
        resume_decision_factory=resume_decision_factory,
    )


def _setup(api_base: str) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider not ready — seed WebUI model via chrome-e2e-model-seed.mjs"
        )
    ensure_e2e_onboarding_complete(api_url=api_base)
    ensure_e2e_hitl_mode(api_url=api_base)


@pytest.fixture(autouse=True)
def _seal_live_http_bootstrap(_chrome_e2e_item_runtime: object | None) -> None:
    """HTTP-only LIVE tests never call ``open_mcp_page`` — seal BODY without Chrome page open."""
    _ = _chrome_e2e_item_runtime
    try:
        from e2e_session_runtime.lifecycle import complete_bootstrap_phase

        complete_bootstrap_phase(phase_label="live_http_no_browser")
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _pin_hitl_before_stream(_chrome_e2e_item_runtime: object | None) -> Iterator[None]:
    _ = _chrome_e2e_item_runtime
    pin_and_verify_hitl_mode(get_e2e_api_url())
    yield


@pytest.fixture
def _live_client(_chrome_e2e_item_runtime: object | None) -> Iterator[httpx.Client]:
    _ = _chrome_e2e_item_runtime
    api_base = get_e2e_api_url()
    _setup(api_base)
    with httpx.Client(base_url=api_base, timeout=60.0) as client:
        yield client
    ensure_e2e_hitl_mode(api_url=api_base)


@pytest.fixture
def _delegating_agent_id(_live_client: httpx.Client) -> str:
    return _create_delegating_agent(_live_client, get_e2e_api_url())


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(1200)
def test_subagent_interrupt_live_approve(
    _live_client: httpx.Client, _delegating_agent_id: str
) -> None:
    chat_id = str(uuid.uuid4())
    target_dir = f"/tmp/myrm_live_interrupt_approve_{uuid.uuid4().hex[:6]}"

    def _decision(_events: list[dict[str, object]]) -> list[dict[str, object]]:
        return [{"type": "approve", "feedback": "Looks good from LIVE E2E"}]

    _run_interrupt_case(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        _delegating_agent_id,
        resume_decision_factory=_decision,
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(1200)
def test_subagent_interrupt_live_allow_always(
    _live_client: httpx.Client, _delegating_agent_id: str
) -> None:
    chat_id = str(uuid.uuid4())
    target_dir = f"/tmp/myrm_live_interrupt_always_{uuid.uuid4().hex[:6]}"

    def _decision(_events: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "type": "approve",
                "feedback": "Always allow from LIVE E2E",
                "extensions": {"allowAlways": {"tool": True}},
            }
        ]

    _run_interrupt_case(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        _delegating_agent_id,
        resume_decision_factory=_decision,
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(1200)
def test_subagent_interrupt_live_edit(
    _live_client: httpx.Client, _delegating_agent_id: str
) -> None:
    chat_id = str(uuid.uuid4())
    target_dir = f"/tmp/myrm_live_interrupt_edit_{uuid.uuid4().hex[:6]}"

    def _decision(events: list[dict[str, object]]) -> list[dict[str, object]]:
        original = _extract_subagent_tool_args(events)
        metadata_keys = {
            "command_spans",
            "commandSpans",
            "command_span_risks",
            "commandSpanRisks",
            "command_span_reasons",
            "commandSpanReasons",
        }
        edited = {k: v for k, v in original.items() if k not in metadata_keys}
        edited["command"] = "echo edited_live_e2e_ok"
        return [
            {"type": "edit", "args": edited, "feedback": "Edited command from LIVE E2E"}
        ]

    _run_interrupt_case(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        _delegating_agent_id,
        resume_decision_factory=_decision,
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(1200)
def test_subagent_interrupt_live_reject(
    _live_client: httpx.Client, _delegating_agent_id: str
) -> None:
    chat_id = str(uuid.uuid4())
    target_dir = f"/tmp/myrm_live_interrupt_reject_{uuid.uuid4().hex[:6]}"

    def _decision(_events: list[dict[str, object]]) -> list[dict[str, object]]:
        return [{"type": "reject", "feedback": "Rejected from LIVE E2E"}]

    _run_interrupt_case(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        _delegating_agent_id,
        resume_decision_factory=_decision,
    )
