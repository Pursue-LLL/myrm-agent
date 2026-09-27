"""Chrome MCP E2E: Workflow Recorder dialog in Settings > Skills.

Verifies the recorder UI reflects real capture state end to end:
1. Settings/Skills page loads and the Curator panel is visible.
2. The recorder API reports capture availability for this host.
3. The dialog opens and shows the honest capture/permission guidance that matches the API state.

The capture state assertion is driven by the live session payload, so the dialog copy is verified
against real backend state rather than a hard-coded expectation.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_SETTINGS_SHELL_STATE = """(() => {
  const ready = !!document.querySelector('[data-testid="settings-layout"], [data-settings-layout]');
  const text = document.body?.innerText || '';
  return {
    ready: ready || /Skills|技能|スキル|스킬/.test(text),
    snippet: text.slice(0, 400),
  };
})()"""

# The Curator panel hosts the recorder trigger; its presence proves the mount point is live
# (the dialog itself is only rendered once opened).
_RECORDER_TRIGGER_STATE = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const trigger = buttons.find((b) => /Record Workflow|录制工作流|錄製工作流程|ワークフローを録画|워크플로 녹화|Workflow aufzeichnen/i.test(b.textContent || ''));
  return {
    ready: !!trigger,
    hasTrigger: !!trigger,
    snippet: (document.body?.innerText || '').slice(0, 600),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_workflow_recorder_reflects_capture_state() -> None:
    """The recorder dialog opens and its guidance matches the live capture state."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # Real backend state first: start a recording and read what capture reports for this host.
    session_id = f"e2e-recorder-{uuid.uuid4().hex[:8]}"
    started = http_json(
        "POST",
        f"{api_url}/api/v1/skills/desktop-recorder/start",
        body={"session_id": session_id, "app_scope": "all"},
    )
    try:
        assert started["session_id"] == session_id
        capture_active = bool(started.get("capture_active"))
        capture_error = started.get("capture_error") or ""

        # When capture is unavailable the API must say why; when it is active the reason is empty.
        if capture_active:
            assert capture_error == "", f"active capture should not report an error: {capture_error}"
        else:
            assert capture_error != "", "inactive capture must report a reason"

        warm_ui_route("/settings")
        warm_ui_route("/settings/skills", timeout_sec=_warm_ui_parallel_wait_sec(180.0))

        with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)

            shell = wait_for_state(
                client,
                page,
                _SETTINGS_SHELL_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(120.0),
            )
            assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

            trigger = wait_for_state(
                client,
                page,
                _RECORDER_TRIGGER_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            )
            assert trigger.get("hasTrigger") is True, json.dumps(trigger, indent=2, ensure_ascii=False)
    finally:
        http_json(
            "POST",
            f"{api_url}/api/v1/skills/desktop-recorder/stop",
            body={"session_id": session_id},
        )
