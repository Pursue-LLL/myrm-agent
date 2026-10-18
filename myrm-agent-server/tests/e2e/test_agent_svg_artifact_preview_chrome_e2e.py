"""Chrome E2E: a live agent writes an SVG file and the workspace preview renders it.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP CDP test infrastructure)
- cdp_chat.support::fetch_chat_messages, wait_e2e_provider_ready (POS: live chat + provider readiness)
- tests.support.e2e_provider_seed::seed_live_e2e_providers (POS: live provider seeding)
- app/api/chats/test_fixtures/rich_media_preview (POS: workspace + chat seed route)

[OUTPUT]
- test_agent_svg_artifact_preview_chrome_e2e: a real model turn writes
  agent_drawn.svg into the seeded chat workspace, and the workspace browser
  preview renders the new file through SvgPreview without a load error

[POS]
LIVE lane Chrome E2E for the SvgPreview delivery (topic_01 #18): covers the real
user flow of asking the agent for an SVG and previewing the produced artifact.
"""

from __future__ import annotations

import json
import os
import sys
import time
from urllib.parse import urlencode

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from cdp_chat.support import (  # noqa: E402
    fetch_chat_messages,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402

_AGENT_SVG_FILENAME = "agent_drawn.svg"
_AGENT_SVG_PROMPT = (
    "请在我的工作区创建一个 SVG 文件，文件名为 agent_drawn.svg：尺寸 200x120，"
    "包含一个蓝色圆形和一行文字 Hello SVG。请直接用文件写入工具完成，不要询问确认。"
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_ATTACH_CHAT_JS_TEMPLATE = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {
    return { ok: false, err: 'no-bridge' };
  }
  await bridge.attachToChat(%s);
  const domDeadline = Date.now() + 30_000;
  while (Date.now() < domDeadline) {
    if (
      document.querySelector('[data-message-end]')
      || document.querySelector('[data-chat-input]')
    ) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const snap = bridge.turnSnapshot?.() ?? {};
  return { ok: snap.chatId === %s, snap };
})()"""

_SEND_TURN_JS_TEMPLATE = """(async () => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, err: 'no-sendChatMessage' };
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage(%s, {
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  });
  return { ...result, usersBefore };
})()"""

_OPEN_WORKSPACE_TAB_JS = """(() => {
  const tab = Array.from(document.querySelectorAll('button')).find((b) =>
    /Files|文件|檔案/.test(b.textContent || ''),
  );
  if (tab) tab.click();
  return { ok: Boolean(tab), ready: Boolean(tab), text: tab?.textContent || '' };
})()"""

_CLICK_FILE_ROW_JS_TEMPLATE = """(() => {
  const name = %s;
  const span = document.querySelector('span[title="' + name.replace(/"/g, '\\\\"') + '"]');
  const btn = span ? span.closest('button') : null;
  if (btn) btn.click();
  return { ok: Boolean(btn), ready: Boolean(btn) };
})()"""

_PREVIEW_READY_JS = """(() => ({
  ready: Boolean(document.querySelector('[data-testid="workspace-file-preview"]')),
  bodyLength: (document.body?.innerText || '').length,
}))()"""

_AGENT_SVG_PREVIEW_READY_JS = """(() => {
  const panel = document.querySelector('[data-testid="workspace-file-preview"]');
  const contentSvg = panel
    ? Array.from(panel.querySelectorAll('svg')).find((s) => {
        const vb = (s.getAttribute('viewBox') || '').split(/[\\s,]+/).map(Number);
        if (vb.length === 4 && (vb[2] > 40 || vb[3] > 40)) return true;
        const w = Number(s.getAttribute('width') || 0);
        const h = Number(s.getAttribute('height') || 0);
        return w > 40 || h > 40;
      })
    : undefined;
  const innerText = panel?.innerText || '';
  return {
    ready: Boolean(contentSvg),
    bodyLength: (document.body?.innerText || '').length,
    hasPanel: Boolean(panel),
    svgCount: panel ? panel.querySelectorAll('svg').length : 0,
    panelTextSample: innerText.slice(0, 240),
    hasSpinner: Boolean(panel?.querySelector('.animate-spin')),
    hasError: /Failed to load|加载失败|載入失敗/.test(innerText),
  };
})()"""


def _entries_from_listing(listing: object) -> list[object]:
    if not isinstance(listing, dict):
        return []
    payload = listing.get("data")
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return payload["entries"]
    if isinstance(listing.get("entries"), list):
        return listing["entries"]
    return []


def _workspace_file_present(api_url: str, workspace_dir: str, filename: str) -> bool:
    query = urlencode({"path": workspace_dir, "depth": "2"})
    try:
        listing = http_json("GET", f"{api_url}/api/v1/files/browse/files?{query}")
    except Exception:  # noqa: BLE001 - transient listing failures keep the wait loop alive
        return False
    entries = _entries_from_listing(listing)
    if not entries:
        return False

    def _walk(items: list[object]) -> bool:
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("name") == filename:
                return True
            children = item.get("children")
            if isinstance(children, list) and _walk(children):
                return True
        return False

    return _walk(entries)


def _wait_for_agent_svg(api_url: str, workspace_dir: str, timeout_sec: float = 210.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_listing: object = None
    query = urlencode({"path": workspace_dir, "depth": "2"})
    while time.monotonic() < deadline:
        if _workspace_file_present(api_url, workspace_dir, _AGENT_SVG_FILENAME):
            return
        try:
            last_listing = http_json("GET", f"{api_url}/api/v1/files/browse/files?{query}")
        except Exception as exc:  # noqa: BLE001 - surface the last failure in the final assert
            last_listing = str(exc)
        time.sleep(3.0)
    pytest.fail(
        f"agent did not write {_AGENT_SVG_FILENAME} within {timeout_sec}s; "
        f"last listing={json.dumps(last_listing, ensure_ascii=False)[:600]}"
    )


def _wait_assistant_reply(
    chat_id: str,
    api_url: str,
    *,
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    """Poll chat messages until the live model's assistant reply lands."""
    deadline = time.monotonic() + timeout_sec
    last_messages: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        last_messages = [
            m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        assistant = next(
            (
                m
                for m in reversed(last_messages)
                if isinstance(m, dict) and m.get("role") == "assistant"
            ),
            None,
        )
        if isinstance(assistant, dict):
            content = assistant.get("content") or assistant.get("message") or ""
            if isinstance(content, str) and content.strip():
                return assistant
        time.sleep(3.0)
    pytest.fail(
        f"assistant reply not received within {timeout_sec}s for chat {chat_id}; "
        f"messages={json.dumps(last_messages, ensure_ascii=False)[:600]}"
    )


def _open_agent_svg_preview(client: object, page: object) -> None:
    """Click the agent-written file row and wait for the preview panel, retrying clicks."""
    click_js = _CLICK_FILE_ROW_JS_TEMPLATE % json.dumps(_AGENT_SVG_FILENAME)
    deadline = time.monotonic() + 90.0
    last_state: object = None
    while time.monotonic() < deadline:
        clicked = client.evaluate(page, click_js, timeout_sec=10.0)  # type: ignore[attr-defined]
        if isinstance(clicked, dict) and clicked.get("ok"):
            preview = client.evaluate(page, _PREVIEW_READY_JS, timeout_sec=10.0)  # type: ignore[attr-defined]
            last_state = preview
            if isinstance(preview, dict) and preview.get("ready"):
                return
        else:
            last_state = clicked
        time.sleep(1.0)
    pytest.fail(
        f"workspace preview panel did not open for {_AGENT_SVG_FILENAME}; "
        f"last={json.dumps(last_state, ensure_ascii=False)[:400]}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_agent_svg_artifact_preview_chrome_e2e() -> None:
    """Real model task -> agent writes an SVG file -> workspace preview renders it."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-rich-media-preview-fixture",
    )
    assert isinstance(seeded, dict), seeded
    chat_id = str(seeded.get("chat_id") or "")
    workspace_dir = str(seeded.get("workspace_dir") or "")
    assert chat_id.startswith("e2ermd"), seeded
    assert workspace_dir, seeded

    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route("/")
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]

        bridge_ready = wait_for_react_e2e_bridge(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            timeout_sec=120.0,
            page_url=target_url,
        )
        assert bridge_ready.get("ready") is True, json.dumps(bridge_ready, ensure_ascii=False)

        chat_id_json = json.dumps(chat_id)
        attached = client.evaluate(  # type: ignore[attr-defined]
            page,
            _ATTACH_CHAT_JS_TEMPLATE % (chat_id_json, chat_id_json),
            timeout_sec=60.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        # 1. Ask the live model to write the SVG deliverable into the workspace
        sent = client.evaluate(  # type: ignore[attr-defined]
            page,
            _SEND_TURN_JS_TEMPLATE % json.dumps(_AGENT_SVG_PROMPT),
            timeout_sec=60.0,
        )
        assert isinstance(sent, dict) and sent.get("ok") is not False, sent

        # 2. Wait until the agent-written file lands in the workspace
        _wait_for_agent_svg(api_url, workspace_dir)

        # 3. Open the workspace browser, preview the new file, and verify SvgPreview
        tab_state = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _OPEN_WORKSPACE_TAB_JS,
            timeout_sec=60.0,
        )
        assert tab_state.get("ok") is True, json.dumps(tab_state, ensure_ascii=False)

        _open_agent_svg_preview(client, page)

        svg_state = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _AGENT_SVG_PREVIEW_READY_JS,
            timeout_sec=30.0,
        )
        assert svg_state.get("ready") is True, json.dumps(svg_state, ensure_ascii=False)
        assert svg_state.get("hasError") is False, json.dumps(svg_state, ensure_ascii=False)

        # 4. The live model answered the turn (assistant message exists)
        reply = _wait_assistant_reply(chat_id, api_url)
        assert str(reply.get("role")) == "assistant", reply
