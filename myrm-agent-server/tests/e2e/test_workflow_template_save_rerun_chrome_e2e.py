"""Chrome LIVE E2E: Dynamic Workflow save-from-run → pinned template rerun."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


def _workflow_template_id() -> str:
    """Per-run template id so parallel SHARED runs never overwrite each other's template."""
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    suffix = run_id[:12] if run_id else uuid.uuid4().hex[:12]
    return f"e2e-dw-rerun-{suffix}"


from cdp_chat.support import (  # noqa: E402
    DISMISS_MODALS_JS,
    E2E_API_BINDING_PROBE_JS,
    _collect_agent_stream_events,
    cancel_e2e_chat_agent_via_api,
    create_e2e_chat_via_api,
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)

from tests.api.agent.utils import get_model_selection  # noqa: E402
from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _ensure_e2e_private_api_live,
    _resolve_dw_stream_message_id,
    dismiss_blocking_modals,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_chat_send_idle,
    wait_for_dw_stream_done_via_api,
    wait_for_react_e2e_bridge,
    wait_for_state,
    wait_for_workflow_plan_card,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

_BRIDGE_READY_JS = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.sendChatMessage === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.setWorkflowMode === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.ensureChatSession === 'function',
}))()"""

_PREPARE_DW_TURN_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) {
    return { ok: false, err: 'no-bridge' };
  }
  await bridge.ensureChatSession?.({ preserveActionMode: true });
  bridge.setWorkflowMode?.(true);
  return {
    ok: bridge.isWorkflowMode?.() === true,
    sendReady: bridge.isSendReady?.() === true,
  };
})()"""

_RESOLVE_CHAT_ID_JS = """(() => ({
  chatId: window.__MYRM_E2E_CHAT__?.turnSnapshot?.().chatId ?? null,
}))()"""

E2E_PROMPT = (
    "Orchestrate a workflow: spawn exactly one generalPurpose sub-agent "
    "to summarize the phrase HELLO_DW_TEMPLATE_RERUN in one sentence, then print JSON results."
)

_RERUN_QUERY = "Rerun pinned template: summarize HELLO_DW_TEMPLATE_RERUN again in one short sentence."

_KICKOFF_DW_JS = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) {{
    return {{ ok: false, err: 'no-send' }};
  }}
  return await bridge.sendChatMessage({json.dumps(E2E_PROMPT)}, {{
    waitForStreamCompletion: false,
    preserveActionMode: true,
  }});
}})()"""

_STREAM_TIMEOUT_SEC = 420.0
_DW_IDLE_TIMEOUT_SEC = 180.0


def _agent_stream_turn(
    *,
    api_base: str,
    chat_id: str,
    query: str,
    message_id: str,
    use_workflow: bool = True,
    workflow_template_id: str | None = None,
    timeout_sec: float = _STREAM_TIMEOUT_SEC,
    idle_timeout_sec: float = _DW_IDLE_TIMEOUT_SEC,
    max_attempts: int = 6,
) -> dict[str, object]:
    resolved_base = api_base.rstrip("/")
    last: dict[str, object] = {}
    for attempt in range(max_attempts):
        if attempt > 0:
            cancel_e2e_chat_agent_via_api(chat_id, api_url=resolved_base)
            time.sleep(min(5.0, 1.5 * attempt))
        payload: dict[str, object] = {
            "messageId": message_id if attempt == 0 else f"{message_id}-r{attempt}",
            "chatId": chat_id,
            "query": query,
            "actionMode": "agent",
            "modelSelection": get_model_selection(),
            "enableWebSearch": False,
            "agentConfig": {
                "enabledBuiltinTools": ["answer_tool", "memory", "structured_clarify"],
                "skillIds": [],
            },
            "use_workflow": use_workflow,
            "memoryRequireConfirmation": False,
            "enableMemoryAutoExtraction": False,
        }
        if workflow_template_id:
            payload["workflow_template_id"] = workflow_template_id
        last = _collect_agent_stream_events(
            payload,
            api_url=resolved_base,
            timeout_sec=timeout_sec,
            idle_timeout_sec=idle_timeout_sec,
        )
        error = last.get("error")
        if not isinstance(error, dict):
            return last
        if error.get("error_type") != "AgentBusyError":
            return last
    return last


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workflow_template_save_and_pinned_rerun_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Save orchestration script from a DW run, then rerun via pinned template_id."""
    _ = e2e_resource_ledger
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail(
            "Provider not ready — run ./myrm ready --chrome then ./myrm test -m chrome_e2e "
            "myrm-agent/myrm-agent-server/tests/e2e/test_workflow_template_save_rerun_chrome_e2e.py",
        )

    ensure_e2e_yolo_mode()
    ui_url = get_e2e_ui_url()
    api_base = get_e2e_api_url().rstrip("/")

    with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, DISMISS_MODALS_JS, timeout_sec=10.0)
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=90.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=ui_url)
        _ensure_e2e_private_api_live(client, page, timeout_sec=120.0)

        binding = client.evaluate(page, E2E_API_BINDING_PROBE_JS, timeout_sec=10.0)
        assert isinstance(binding, dict), binding
        bound_api = str(binding.get("apiBase") or "").rstrip("/")
        assert bound_api == api_base, f"E2E API binding drift: bound={bound_api!r} expected={api_base!r}"

        prepared = client.evaluate(page, _PREPARE_DW_TURN_JS, timeout_sec=60.0)
        assert isinstance(prepared, dict), prepared
        assert prepared.get("ok") is True, f"Workflow mode prep failed: {prepared}"

        kickoff = client.evaluate(page, _KICKOFF_DW_JS, timeout_sec=120.0)
        assert isinstance(kickoff, dict), kickoff
        assert kickoff.get("ok") is True, f"Kickoff failed: {kickoff}"

        chat_id = str(kickoff.get("chatId") or "").strip()
        if not chat_id:
            resolved = client.evaluate(page, _RESOLVE_CHAT_ID_JS, timeout_sec=15.0)
            if isinstance(resolved, dict):
                chat_id = str(resolved.get("chatId") or "").strip()
        assert chat_id, f"Missing chatId after kickoff: {kickoff}"

        stream_message_id = _resolve_dw_stream_message_id(client, page)
        if not stream_message_id:
            stream_probe = client.evaluate(
                page,
                """(() => ({
                  streamMessageId:
                    window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.streamRequestMessageId ?? null,
                }))()""",
                timeout_sec=15.0,
            )
            if isinstance(stream_probe, dict):
                stream_message_id = str(stream_probe.get("streamMessageId") or "").strip() or None

        plan = wait_for_workflow_plan_card(
            client,
            page,
            page_url=ui_url,
            timeout_sec=420.0,
            chat_id=chat_id,
            stream_message_id=stream_message_id,
            api_base=api_base,
        )
        assert plan.get("confirmedVia") in {"api", "yolo_skip"}, plan

        stream_done = wait_for_dw_stream_done_via_api(
            api_base=api_base,
            chat_id=chat_id,
            timeout_sec=_STREAM_TIMEOUT_SEC,
        )
        save_message_id = stream_message_id or _resolve_dw_stream_message_id(client, page)
        assert save_message_id, (
            f"Missing stream request messageId for save-from-run (kickoff={kickoff}, stream_done={stream_done})"
        )
        sample = str(stream_done.get("sample") or "")
        assert "myrm_tools" not in sample.lower(), f"DW run failed before script persist: {stream_done}"

        saved = http_json(
            "POST",
            f"{api_base}/api/v1/workflow-templates/from-run",
            {
                "chatId": chat_id,
                "messageId": save_message_id,
                "templateId": _workflow_template_id(),
                "displayName": "E2E DW Rerun",
                "trustLatch": True,
            },
        )
        assert saved.get("templateId") == _workflow_template_id(), saved

        wait_for_chat_send_idle(client, page, timeout_sec=120.0)

        rerun_chat_id = f"e2e-dw-rerun-{uuid.uuid4().hex[:12]}"
        create_e2e_chat_via_api(rerun_chat_id, api_url=api_base)

        rerun_stream = _agent_stream_turn(
            api_base=api_base,
            chat_id=rerun_chat_id,
            query=_RERUN_QUERY,
            message_id=f"e2e-rerun-{uuid.uuid4().hex[:12]}",
            use_workflow=True,
            workflow_template_id=_workflow_template_id(),
            timeout_sec=_STREAM_TIMEOUT_SEC,
        )
        if rerun_stream.get("error"):
            pytest.fail(f"Pinned template rerun agent-stream failed: {rerun_stream}")

        wait_for_dw_stream_done_via_api(
            api_base=api_base,
            chat_id=rerun_chat_id,
            timeout_sec=60.0,
        )
