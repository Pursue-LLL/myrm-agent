"""Live HTTP E2E: subagent high-risk bash approval interrupt → approve/allow-always/edit resume.

Replaces the in-process ``TestClient`` variant (``tests/api/agent/test_subagent_interrupt_e2e.py``)
whose approval events cannot bridge the subagent -> parent stream in a single-process
TestClient. This version talks to the real SHPOIB agent-stream over HTTP, where the
approval middleware + ``ApprovalRegistry`` are fully wired, so the ``approval_required``
interrupt is observable and resumable exactly as a real WebUI user would experience it.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_subagent_interrupt_live_e2e.py
"""

from __future__ import annotations

import json
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

_MAX_RESUME_ROUNDS = 6
_STREAM_TIMEOUT_SEC = 300.0

_DELEGATE_QUERY_TMPL = (
    "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'test_bash'，"
    "并且必须将 wait 参数设置为 true（同步等待子任务完成，不要异步）。"
    "让它执行一条bash命令: `rm -rf {target_dir}`。"
    "注意：必须使用原生函数调用（Native Tool Calling / Function Calling），绝对不要在文本中输出 XML 格式的工具调用！"
)


def _build_request(
    chat_id: str,
    message_id: str,
    query: str,
    *,
    resume_value: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    req: dict[str, object] = {
        "query": query,
        "chatId": chat_id,
        "messageId": message_id,
        "actionMode": "general",
        "ephemeralSubagents": {
            "test_bash": {
                "system_prompt": "You are a bash execution worker.",
                "tools": ["bash_code_execute_tool"],
            }
        },
    }
    if resume_value is not None:
        req["resumeValue"] = {"decisions": resume_value}
    return req


def _consume_stream(
    client: httpx.Client,
    api_base: str,
    payload: dict[str, object],
) -> tuple[str | None, list[dict[str, object]], list[dict[str, object]]]:
    """Stream agent-stream once. Returns (action_type, events, errors)."""
    events: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    action_type: str | None = None
    with client.stream(
        "POST",
        f"{api_base}/api/v1/agents/agent-stream",
        json=payload,
        timeout=_STREAM_TIMEOUT_SEC,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            event_type = event.get("type")
            if event_type == "approval_required":
                data = event.get("data")
                if isinstance(data, dict):
                    action_type = data.get("action_type")
                    if not isinstance(action_type, str):
                        action_type = "tool_approval"
            elif event_type == "error":
                errors.append(event)
    return action_type, events, errors


def _extract_subagent_tool_args(events: list[dict[str, object]]) -> dict[str, object]:
    for event in events:
        if event.get("type") != "approval_required":
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


def _run_interrupt_flow(
    client: httpx.Client,
    api_base: str,
    chat_id: str,
    target_dir: str,
    *,
    resume_decision_factory: Callable[
        [list[dict[str, object]]], list[dict[str, object]]
    ],
) -> None:
    message_id = str(uuid.uuid4())
    query = _DELEGATE_QUERY_TMPL.format(target_dir=target_dir)
    resume_value: list[dict[str, object]] | None = None
    approval_seen = False

    for _round in range(_MAX_RESUME_ROUNDS):
        heartbeat_once()
        payload = _build_request(chat_id, message_id, query, resume_value=resume_value)
        action_type, events, errors = _consume_stream(client, api_base, payload)

        if action_type == "subagent_approval":
            approval_seen = True
            resume_value = resume_decision_factory(events)
            message_id = str(uuid.uuid4())
            query = ""
            # One more round resumes the interrupted agent.
            continue

        if errors:
            raise AssertionError(f"agent-stream errors before approval: {errors}")

        if action_type in (None, "tool_approval"):
            # Main agent wants approval for delegate_task_tool itself — auto-approve.
            resume_value = [
                {"type": "approve", "feedback": "Auto-approve delegate_task_tool"}
            ]
            message_id = str(uuid.uuid4())
            query = ""
            continue

        break

    if not approval_seen:
        raise AssertionError(
            f"No subagent_approval interrupt observed after {_MAX_RESUME_ROUNDS} rounds; "
            f"last action_type={action_type!r} events={[e.get('type') for e in events]}"
        )

    # The final resume turn must complete.
    heartbeat_once()
    payload = _build_request(chat_id, message_id, "", resume_value=resume_value)
    _action_type, resume_events, resume_errors = _consume_stream(
        client, api_base, payload
    )
    has_end = any(e.get("type") == "message_end" for e in resume_events)
    if not has_end:
        raise AssertionError(
            f"Agent did not complete after approval resume; "
            f"events={[e.get('type') for e in resume_events]} errors={resume_errors}"
        )


def _setup(api_base: str) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider not ready — seed WebUI model via chrome-e2e-model-seed.mjs"
        )
    ensure_e2e_onboarding_complete(api_url=api_base)
    ensure_e2e_hitl_mode(api_url=api_base)


def _new_client(api_base: str) -> httpx.Client:
    return httpx.Client(base_url=api_base, timeout=60.0)


@pytest.fixture
def _live_client(_chrome_e2e_item_runtime: object | None) -> Iterator[httpx.Client]:
    """Bind SHPOIB private runtime before probing provider readiness."""
    _ = _chrome_e2e_item_runtime
    api_base = get_e2e_api_url()
    _setup(api_base)
    with _new_client(api_base) as client:
        yield client
    ensure_e2e_hitl_mode(api_url=api_base)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(600)
def test_subagent_interrupt_live_approve(_live_client: httpx.Client) -> None:
    """Subagent bash approval interrupt → user approves → subagent resumes & completes."""
    chat_id = str(uuid.uuid4())
    target_dir = f"/tmp/myrm_live_interrupt_approve_{uuid.uuid4().hex[:6]}"

    def _decision(_events: list[dict[str, object]]) -> list[dict[str, object]]:
        return [{"type": "approve", "feedback": "Looks good from LIVE E2E"}]

    _run_interrupt_flow(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        resume_decision_factory=_decision,
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(600)
def test_subagent_interrupt_live_allow_always(_live_client: httpx.Client) -> None:
    """Subagent approval resume accepts extensions.allowAlways (Drawer always-allow path)."""
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

    _run_interrupt_flow(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        resume_decision_factory=_decision,
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(600)
def test_subagent_interrupt_live_edit(_live_client: httpx.Client) -> None:
    """Subagent approval resume accepts edit decisions with merged shell args."""
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

    _run_interrupt_flow(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        resume_decision_factory=_decision,
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(600)
def test_subagent_interrupt_live_reject(_live_client: httpx.Client) -> None:
    """Subagent approval reject → command is NOT executed; agent completes after resume."""
    chat_id = str(uuid.uuid4())
    target_dir = f"/tmp/myrm_live_interrupt_reject_{uuid.uuid4().hex[:6]}"

    def _decision(_events: list[dict[str, object]]) -> list[dict[str, object]]:
        return [{"type": "reject", "feedback": "Rejected from LIVE E2E"}]

    _run_interrupt_flow(
        _live_client,
        get_e2e_api_url(),
        chat_id,
        target_dir,
        resume_decision_factory=_decision,
    )
