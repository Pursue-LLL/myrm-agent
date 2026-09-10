"""Real Chrome MCP E2E for Browser Live Co-View (BLCV) bridge contract."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

_BRIDGE_READY_JS = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.getBrowserInspectorSnapshot === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.simulateBrowserViewUpdate === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.simulateBrowserToolStart === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.getDesktopInspectorSnapshot === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.simulateDesktopViewUpdate === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.simulateDesktopControlApprovalRequest === 'function',
  snapshot: window.__MYRM_E2E_CHAT__?.getBrowserInspectorSnapshot?.() ?? null,
}))()"""


def _seed_blcv_chat(api_url: str) -> str:
    chat_id = f"e2e-blvc-{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/chats/",
        {
            "chat_id": chat_id,
            "title": "E2E BLCV Chat",
            "action_mode": "agent",
            "messages": [
                {
                    "messageId": f"e2e-blvc-user-{uuid.uuid4().hex[:8]}",
                    "chatId": chat_id,
                    "role": "user",
                    "content": "BLCV isolation probe",
                    "createdAt": created_at,
                },
                {
                    "messageId": f"e2e-blvc-assistant-{uuid.uuid4().hex[:8]}",
                    "chatId": chat_id,
                    "role": "assistant",
                    "content": "BLCV ready",
                    "createdAt": created_at,
                },
            ],
        },
    )
    return chat_id


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_browser_inspector_blcv_bridge_exposed_in_real_ui() -> None:
    """Chat shell exposes BLCV inspector snapshot bridge for SSE-driven live view."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(ui_url)

    with open_mcp_page(f"{ui_url.rstrip('/')}/") as (client, page):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        assert state.get("ready") is True, state
        snapshot = state.get("snapshot")
        assert isinstance(snapshot, dict), snapshot
        assert snapshot.get("isOpen") is False
        assert snapshot.get("isBrowserActive") is False
        assert snapshot.get("hasScreenshot") is False
        assert snapshot.get("scopedHasScreenshot") is False
        assert snapshot.get("sourceChatId") == ""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_browser_blcv_multi_chat_sse_isolation_in_real_ui() -> None:
    """Background chat SSE must not surface screenshot in foreground pane."""
    ui_url = get_e2e_ui_url()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(ui_url)
    chat_foreground = _seed_blcv_chat(api_url)
    chat_background = _seed_blcv_chat(api_url)

    probe_js = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat || !bridge.simulateBrowserViewUpdate || !bridge.getBrowserInspectorSnapshot) {{
    return {{ ready: false, reason: 'missing-bridge' }};
  }}
  await bridge.attachToChat({json.dumps(chat_foreground)});
  const inject = await bridge.simulateBrowserViewUpdate({json.dumps(chat_background)});
  if (!inject?.ok) return {{ ready: false, reason: 'inject-failed', inject }};
  const snap = bridge.getBrowserInspectorSnapshot();
  const ready =
    snap.hasScreenshot === true &&
    snap.sourceChatId === {json.dumps(chat_background)} &&
    snap.activeChatId === {json.dumps(chat_foreground)} &&
    snap.scopedHasScreenshot === false &&
    snap.isOpen === false;
  return {{ ready, snap }};
}})()"""

    with open_mcp_page(f"{ui_url.rstrip('/')}/") as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        result = wait_for_state(
            client,
            page,
            probe_js,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        assert result.get("ready") is True, result


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_desktop_blcv_multi_chat_sse_isolation_in_real_ui() -> None:
    """Background chat desktop SSE must not surface screenshot in foreground pane."""
    ui_url = get_e2e_ui_url()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(ui_url)
    chat_foreground = _seed_blcv_chat(api_url)
    chat_background = _seed_blcv_chat(api_url)

    probe_js = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat || !bridge.simulateDesktopViewUpdate || !bridge.getDesktopInspectorSnapshot) {{
    return {{ ready: false, reason: 'missing-bridge' }};
  }}
  await bridge.attachToChat({json.dumps(chat_foreground)});
  const inject = await bridge.simulateDesktopViewUpdate({json.dumps(chat_background)});
  if (!inject?.ok) return {{ ready: false, reason: 'inject-failed', inject }};
  const snap = bridge.getDesktopInspectorSnapshot();
  const ready =
    snap.hasScreenshot === true &&
    snap.sourceChatId === {json.dumps(chat_background)} &&
    snap.activeChatId === {json.dumps(chat_foreground)} &&
    snap.scopedHasScreenshot === false &&
    snap.isOpen === false;
  return {{ ready, snap }};
}})()"""

    with open_mcp_page(f"{ui_url.rstrip('/')}/") as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        result = wait_for_state(
            client,
            page,
            probe_js,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        assert result.get("ready") is True, result


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_browser_blcv_tool_start_panel_scoped_to_foreground_chat() -> None:
    """browser_* TOOL_START opens panel only when stream chat matches foreground chat."""
    ui_url = get_e2e_ui_url()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(ui_url)
    chat_foreground = _seed_blcv_chat(api_url)
    chat_background = _seed_blcv_chat(api_url)

    probe_js = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat || !bridge.simulateBrowserToolStart || !bridge.getBrowserInspectorSnapshot) {{
    return {{ ready: false, reason: 'missing-bridge' }};
  }}
  await bridge.attachToChat({json.dumps(chat_foreground)});
  const bgStart = await bridge.simulateBrowserToolStart({json.dumps(chat_background)});
  if (!bgStart?.ok) return {{ ready: false, reason: 'bg-tool-start-failed', bgStart }};
  const afterBg = bridge.getBrowserInspectorSnapshot();
  if (afterBg.isOpen) {{
    return {{ ready: false, reason: 'panel-opened-for-background', afterBg }};
  }}
  const fgStart = await bridge.simulateBrowserToolStart({json.dumps(chat_foreground)});
  if (!fgStart?.ok) return {{ ready: false, reason: 'fg-tool-start-failed', fgStart }};
  const afterFg = bridge.getBrowserInspectorSnapshot();
  const ready =
    afterFg.isOpen === true &&
    afterFg.activeChatId === {json.dumps(chat_foreground)} &&
    afterFg.isBrowserActive === true;
  return {{ ready, afterBg, afterFg }};
}})()"""

    with open_mcp_page(f"{ui_url.rstrip('/')}/") as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        result = wait_for_state(
            client,
            page,
            probe_js,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        assert result.get("ready") is True, result


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_blcv_edge_cases_switch_chat_and_desktop_approval_in_real_ui() -> None:
    """Edge cases: switch to source chat shows scoped view; chat switch closes panel; desktop approval gate."""
    ui_url = get_e2e_ui_url()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(ui_url)
    chat_a = _seed_blcv_chat(api_url)
    chat_b = _seed_blcv_chat(api_url)

    with open_mcp_page(f"{ui_url.rstrip('/')}/") as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )

        step1_js = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat || !bridge.simulateBrowserViewUpdate || !bridge.getBrowserInspectorSnapshot) {{
    return {{ ready: false, reason: 'missing-bridge' }};
  }}
  await bridge.attachToChat({json.dumps(chat_a)});
  const inject = await bridge.simulateBrowserViewUpdate({json.dumps(chat_b)});
  if (!inject?.ok) return {{ ready: false, reason: 'inject-failed', inject }};
  const snap1 = bridge.getBrowserInspectorSnapshot();
  if (!snap1?.hasScreenshot || snap1?.scopedHasScreenshot) {{
    return {{ ready: false, reason: 'step1-failed', snap1 }};
  }}
  await bridge.attachToChat({json.dumps(chat_b)});
  const snap2 = bridge.getBrowserInspectorSnapshot();
  if (!snap2?.scopedHasScreenshot || snap2?.sourceChatId !== {json.dumps(chat_b)}) {{
    return {{ ready: false, reason: 'step2-failed', snap2 }};
  }}
  return {{ ready: true, snap1, snap2 }};
}})()"""

        step2_js = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat || !bridge.simulateBrowserToolStart || !bridge.getBrowserInspectorSnapshot) {{
    return {{ ready: false, reason: 'missing-bridge' }};
  }}
  await bridge.attachToChat({json.dumps(chat_a)});
  const toolStart = await bridge.simulateBrowserToolStart({json.dumps(chat_a)});
  if (!toolStart?.ok) return {{ ready: false, reason: 'tool-start-failed', toolStart }};
  const snapOpen = bridge.getBrowserInspectorSnapshot();
  if (!snapOpen?.isOpen) {{
    return {{ ready: false, reason: 'panel-not-open', snapOpen }};
  }}
  await bridge.attachToChat({json.dumps(chat_b)});
  let closed = false;
  for (let i = 0; i < 30; i++) {{
    const s = bridge.getBrowserInspectorSnapshot();
    if (!s?.isOpen) {{
      closed = true;
      break;
    }}
    await new Promise((r) => setTimeout(r, 100));
  }}
  const snapClose = bridge.getBrowserInspectorSnapshot();
  if (!closed || snapClose?.isOpen) {{
    return {{ ready: false, reason: 'panel-close-failed', snapClose }};
  }}
  return {{ ready: true, snapOpen, snapClose }};
}})()"""

        step3_js = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat || !bridge.simulateDesktopControlApprovalRequest || !bridge.getDesktopInspectorSnapshot) {{
    return {{ ready: false, reason: 'missing-bridge' }};
  }}
  await bridge.attachToChat({json.dumps(chat_a)});
  await bridge.simulateDesktopControlApprovalRequest({json.dumps(chat_b)});
  await new Promise((r) => setTimeout(r, 100));
  const deskBg = bridge.getDesktopInspectorSnapshot();
  if (deskBg?.isOpen) {{
    return {{ ready: false, reason: 'desktop-bg-opened', deskBg }};
  }}
  await bridge.simulateDesktopControlApprovalRequest({json.dumps(chat_a)});
  let opened = false;
  for (let i = 0; i < 30; i++) {{
    const s = bridge.getDesktopInspectorSnapshot();
    if (s?.isOpen) {{
      opened = true;
      break;
    }}
    await new Promise((r) => setTimeout(r, 100));
  }}
  const deskFg = bridge.getDesktopInspectorSnapshot();
  if (!opened || !deskFg?.isOpen) {{
    return {{ ready: false, reason: 'desktop-fg-failed', deskFg }};
  }}
  return {{ ready: true, deskBg, deskFg }};
}})()"""

        res1 = wait_for_state(client, page, step1_js, timeout_sec=45.0)
        assert res1.get("ready") is True, res1

        res2 = wait_for_state(client, page, step2_js, timeout_sec=45.0)
        assert res2.get("ready") is True, res2

        res3 = wait_for_state(client, page, step3_js, timeout_sec=45.0)
        assert res3.get("ready") is True, res3
