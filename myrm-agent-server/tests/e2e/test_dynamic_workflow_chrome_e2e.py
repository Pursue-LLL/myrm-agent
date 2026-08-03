"""Chrome LIVE E2E: Dynamic Workflow toggle → plan confirm card → Run → execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    DISMISS_MODALS_JS,
    ensure_e2e_yolo_mode,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
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
    debug: bridge.debugProviderState?.() ?? null,
  };
})()"""

_PLAN_CARD_WAITING_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Dynamic Workflow Plan|动态工作流计划|ダイナミックワークフロープラン/i.test(text);
  const buttons = [...document.querySelectorAll('button')];
  const hasRun = buttons.some((btn) =>
    /Run Workflow|运行工作流|執行工作流|ワークフローを実行/i.test((btn.textContent || '').trim()),
  );
  return { ready: hasTitle && hasRun, hasTitle, hasRun };
})()"""

_CLICK_RUN_WORKFLOW_JS = """(() => {
  const buttons = [...document.querySelectorAll('button')];
  const runBtn = buttons.find((btn) =>
    /Run Workflow|运行工作流|執行工作流|ワークフローを実行/i.test((btn.textContent || '').trim()),
  );
  if (!runBtn || runBtn.disabled) {
    return { ok: false, err: 'run-button-missing-or-disabled' };
  }
  runBtn.click();
  return { ok: true };
})"""

_STREAM_DONE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const sample = String(snap.lastAssistantSample || '');
  const hasAssistant = sample.trim().length > 20;
  const notStreaming = snap.isStreaming !== true;
  return {
    ready: hasAssistant && notStreaming,
    isStreaming: snap.isStreaming === true,
    sample: sample.slice(0, 240),
  };
})()"""

E2E_PROMPT = (
    "Orchestrate a workflow: spawn exactly one generalPurpose sub-agent "
    "to summarize the phrase HELLO_DW_CHROME in one sentence, then print JSON results."
)

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


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_dynamic_workflow_plan_confirm_and_run_chrome_e2e() -> None:
    """Full UI path: workflow toggle, plan card, confirm, summarized output."""
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail(
            "Provider not ready — run ./myrm ready --chrome then ./myrm test -m chrome_e2e "
            "myrm-agent/myrm-agent-server/tests/e2e/test_dynamic_workflow_chrome_e2e.py",
        )

    ensure_e2e_yolo_mode()
    ui_url = get_e2e_ui_url()

    with E2EResourceLedger(label="dynamic-workflow-chrome-e2e"):
        with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            client.evaluate(page, DISMISS_MODALS_JS, timeout_sec=10.0)
            wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=90.0)

            prepared = client.evaluate(page, _PREPARE_DW_TURN_JS, timeout_sec=60.0)
            assert isinstance(prepared, dict), prepared
            assert prepared.get("ok") is True, f"Workflow mode prep failed: {prepared}"
            assert prepared.get("sendReady") is True, f"Send not ready: {prepared}"

            kickoff = client.evaluate(
                page,
                _KICKOFF_DW_JS,
                timeout_sec=120.0,
            )
            assert isinstance(kickoff, dict), kickoff
            assert kickoff.get("ok") is True, f"Kickoff failed: {kickoff}"

            wait_for_state(client, page, _PLAN_CARD_WAITING_JS, timeout_sec=180.0)

            clicked = client.evaluate(page, _CLICK_RUN_WORKFLOW_JS, timeout_sec=15.0)
            assert isinstance(clicked, dict)
            assert clicked.get("ok") is True, f"Run click failed: {clicked}"

            wait_for_state(client, page, _STREAM_DONE_JS, timeout_sec=300.0)
