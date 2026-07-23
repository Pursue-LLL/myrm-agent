"""Chrome MCP E2E: LiveTerminal → EvictedOutputDrawer (UECD web_fetch spill, READ lane)."""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_FIXTURE_ANSWER = "UECD evicted output E2E fixture answer."
_PAGE_TIMEOUT_MS = 180_000

_PROGRESS_STEPS_READY_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  if (!msg) return {{ ready: false, count: store?.messages?.length ?? 0 }};
  const metaSteps = Array.isArray(msg.metadata?.progressSteps) ? msg.metadata.progressSteps : [];
  const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
  const step = steps.find((s) => s.evicted_file_ref);
  return {{
    ready: !!step?.evicted_file_ref,
    ref: step?.evicted_file_ref || null,
    hasStdout: !!step?.stdout,
  }};
}})()"""

_EXPAND_PROGRESS_PANEL_JS = """(() => {
  const taskHeader = Array.from(document.querySelectorAll('h3')).find(
    (el) => /Task|任务|タスク|작업/.test(el.textContent || ''),
  );
  if (!taskHeader) {
    return { ready: false, reason: 'no-task-header' };
  }
  const headerRow = taskHeader.closest('.flex.items-center.justify-between');
  const card = headerRow?.nextElementSibling;
  if (!(card instanceof HTMLElement)) {
    return { ready: false, reason: 'no-progress-card' };
  }
  card.click();
  return { ready: true, clicked: true };
})()"""

_TERMINAL_PREVIEW_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTruncated = /LARGE OUTPUT TRUNCATED|输出已截断|出力を切り詰め/.test(text);
  return { ready: hasTruncated, preview: text.slice(0, 400) };
})()"""

_VIEW_FULL_OUTPUT_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /View Full Output|查看完整输出|完整输出を表示|전체 출력 보기/.test(el.textContent || ''),
  );
  if (!btn) {
    return { ready: false, clicked: false };
  }
  btn.click();
  return { ready: true, clicked: true };
})()"""


def _drawer_ready_js(marker_line: str) -> str:
    encoded = json.dumps(marker_line)
    return f"""(() => {{
  const text = document.body?.innerText || '';
  return {{
    ready: text.includes({encoded}),
    sample: text.slice(0, 500),
  }};
}})()"""


def _drawer_expired_js() -> str:
    return """(() => {
  const modal = document.querySelector('.fixed.inset-0.z-50');
  const text = modal?.textContent || document.body?.innerText || '';
  return {
    ready: /输出已过期|Output Expired|Content Expired/.test(text),
    hasModal: !!modal,
    sample: text.slice(0, 400),
  };
})()"""

_CHAT_ROUTE_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="app-layout"]'),
}))()"""


def _seed_uecd_fixture(api_base: str, *, variant: str = "full") -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_base}/api/v1/chats/test/seed-evicted-live-terminal-fixture?variant={variant}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2euecd")
    return seeded


def _wait_fixture_assistant_via_api(api_base: str, chat_id: str, *, timeout_sec: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/chats/{chat_id}/messages")
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                messages = data.get("messages")
                if isinstance(messages, list):
                    last_count = len(messages)
                    assistant = next(
                        (
                            item
                            for item in messages
                            if item.get("role") == "assistant"
                            and _FIXTURE_ANSWER in str(item.get("content") or "")
                        ),
                        None,
                    )
                    if assistant is not None:
                        meta = assistant.get("metadata") if isinstance(assistant.get("metadata"), dict) else {}
                        steps = meta.get("progressSteps")
                        if isinstance(steps, list) and steps and steps[0].get("evicted_file_ref"):
                            return
        time.sleep(0.5)
    raise AssertionError(
        f"Fixture assistant not ready via API for chat {chat_id} after {timeout_sec:.0f}s "
        f"(last_message_count={last_count})"
    )


def _run_drawer_flow(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    marker_line: str | None,
    expect_expired: bool,
) -> None:
    dismiss_blocking_modals(client, page)
    loaded = wait_for_state(client, page, _PROGRESS_STEPS_READY_JS, timeout_sec=120.0)
    assert loaded.get("ready") is True, json.dumps(loaded, ensure_ascii=False)

    expanded = wait_for_state(client, page, _EXPAND_PROGRESS_PANEL_JS, timeout_sec=30.0)
    assert expanded.get("clicked") is True, json.dumps(expanded, ensure_ascii=False)

    if not expect_expired:
        terminal = wait_for_state(client, page, _TERMINAL_PREVIEW_JS, timeout_sec=60.0)
        assert terminal.get("ready") is True, json.dumps(terminal, ensure_ascii=False)

    clicked = wait_for_state(client, page, _VIEW_FULL_OUTPUT_JS, timeout_sec=60.0)
    assert clicked.get("clicked") is True, json.dumps(clicked, ensure_ascii=False)

    if expect_expired:
        drawer = wait_for_state(client, page, _drawer_expired_js(), timeout_sec=45.0)
    else:
        assert marker_line is not None
        drawer = wait_for_state(client, page, _drawer_ready_js(marker_line), timeout_sec=45.0)
    assert drawer.get("ready") is True, json.dumps(drawer, ensure_ascii=False)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(360)
def test_live_terminal_evicted_drawer_reads_uecd_spill_and_expired() -> None:
    """One SHPOIB backend + one Chrome tab: full spill read, then navigate to expired chat."""
    api_base = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    seed_full = _seed_uecd_fixture(api_base, variant="full")
    chat_full = str(seed_full["chat_id"])
    marker_line = str(seed_full["marker_line"])
    _wait_fixture_assistant_via_api(api_base, chat_full)

    seed_expired = _seed_uecd_fixture(api_base, variant="expired")
    chat_expired = str(seed_expired["chat_id"])
    _wait_fixture_assistant_via_api(api_base, chat_expired)

    prepare_e2e_ui_session(api_base)
    warm_ui_route(f"/{chat_full}")
    warm_ui_route(f"/{chat_expired}")

    with open_mcp_page(f"{ui_url}/{chat_full}", timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        _run_drawer_flow(
            client,
            page,
            marker_line=marker_line,
            expect_expired=False,
        )

        client.navigate(page, f"{ui_url}/{chat_expired}", timeout_ms=_PAGE_TIMEOUT_MS)
        wait_for_state(client, page, _CHAT_ROUTE_READY_JS, timeout_sec=90.0)

        _run_drawer_flow(
            client,
            page,
            marker_line=None,
            expect_expired=True,
        )
