"""Real Chrome MCP E2E for RevertFiles: Undo → diff popover → Confirm → resync."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_FIXTURE_ANSWER = "Revert E2E fixture answer with file change."

_UNDO_BUTTON_READY_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {{
    if (!(node.textContent || '').includes(target)) continue;
    let el = node.parentElement;
    for (let depth = 0; depth < 20 && el; depth += 1) {{
      const btn = Array.from(el.querySelectorAll('button[title]')).find((candidate) => {{
        const title = candidate.getAttribute('title') || '';
        return /Undo file changes|撤销文件变更/i.test(title);
      }});
      if (btn) {{
        return {{ ready: true, title: btn.getAttribute('title') || null }};
      }}
      el = el.parentElement;
    }}
  }}
  return {{ ready: false }};
}})()"""

_CLICK_UNDO_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {{
    if (!(node.textContent || '').includes(target)) continue;
    let el = node.parentElement;
    for (let depth = 0; depth < 20 && el; depth += 1) {{
      const btn = Array.from(el.querySelectorAll('button[title]')).find((candidate) => {{
        const title = candidate.getAttribute('title') || '';
        return /Undo file changes|撤销文件变更/i.test(title);
      }});
      if (btn) {{
        btn.click();
        return {{ clicked: true, title: btn.getAttribute('title') || null }};
      }}
      el = el.parentElement;
    }}
  }}
  return {{ clicked: false }};
}})()"""

_POPOVER_READY_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const text = popover?.textContent || document.body?.innerText || '';
  const hasConfirm = /Undo these changes\\?|撤销这些变更？/i.test(text);
  const hasFile = /revert_e2e_fixture\\.txt/i.test(text);
  const hasAction = /Confirm revert|确认撤销/i.test(text);
  return { ready: !!popover && hasConfirm && hasFile && hasAction, sample: text.slice(0, 400) };
})()"""

_CLICK_CONFIRM_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const scope = popover || document;
  const btn = Array.from(scope.querySelectorAll('button')).find((el) => {
    const label = (el.textContent || '').trim();
    return /Confirm revert|确认撤销/i.test(label);
  });
  if (!btn) return { clicked: false };
  btn.click();
  return { clicked: true };
})()"""

_SUCCESS_STATE_JS = """(() => {
  const resyncSeen = window.__MYRM_REVERT_RESYNC__ === true;
  const greenCheck = !!document.querySelector('span.text-green-600 svg, span.text-green-400 svg');
  return { ready: resyncSeen || greenCheck, resyncSeen, greenCheck };
})()"""

_HOOK_RESYNC_JS = """(() => {
  window.__MYRM_REVERT_RESYNC__ = false;
  window.addEventListener('app_resync_required', () => {
    window.__MYRM_REVERT_RESYNC__ = true;
  }, { once: true });
  return { hooked: true };
})()"""


_PROBE_REVERT_FETCH_JS = f"""(() => {{
  return (async () => {{
    const chatId = location.pathname.replace(/^\\//, '');
    const store = window.__myrmChatStore?.getState?.();
    const msg = (store?.messages || []).find(
      (item) => item.role === 'assistant' && (item.content || '').includes({json.dumps(_FIXTURE_ANSWER)}),
    );
    if (!msg) {{
      return {{ ok: false, err: 'fixture-message-missing', chatId, count: store?.messages?.length ?? 0 }};
    }}
    const res = await fetch(`/api/v1/files/revert/changes/${{chatId}}/${{msg.messageId}}`);
    const body = await res.text();
    return {{
      ok: res.ok && body.startsWith('[') && body.includes('revert_e2e_fixture.txt'),
      status: res.status,
      chatId,
      messageId: msg.messageId,
      body: body.slice(0, 300),
    }};
  }})();
}})()"""


def _seed_revert_fixture(api_url: str, *, variant: str = "modify") -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-revert-fixture?variant={variant}")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    ui_path = str(seeded.get("ui_path") or "")
    assert chat_id.startswith("e2erevert")
    assert len(message_id) >= 8
    assert ui_path == f"/{chat_id}"
    return seeded


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_revert_files_undo_diff_confirm_flow() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_revert_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    message_id = str(seeded["message_id"])
    file_path = str(seeded["file_path"])

    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        client.evaluate(page, _HOOK_RESYNC_JS, timeout_sec=10.0)

        probe = wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg, count: store?.messages?.length ?? 0 }};
            }})()""",
            timeout_sec=90.0,
        )
        assert probe.get("ready") is True, json.dumps(probe, ensure_ascii=False)

        fetch_probe = client.evaluate(page, _PROBE_REVERT_FETCH_JS, timeout_sec=30.0)
        assert isinstance(fetch_probe, dict) and fetch_probe.get("ok") is True, json.dumps(
            fetch_probe,
            ensure_ascii=False,
        )

        button = wait_for_state(client, page, _UNDO_BUTTON_READY_JS, timeout_sec=30.0)
        assert button.get("ready") is True, json.dumps(button, ensure_ascii=False)

        clicked = client.evaluate(page, _CLICK_UNDO_JS, timeout_sec=10.0)
        assert isinstance(clicked, dict) and clicked.get("clicked") is True, clicked

        popover = wait_for_state(client, page, _POPOVER_READY_JS, timeout_sec=45.0)
        assert popover.get("ready") is True, json.dumps(popover, ensure_ascii=False)

        confirmed = client.evaluate(page, _CLICK_CONFIRM_JS, timeout_sec=10.0)
        assert isinstance(confirmed, dict) and confirmed.get("clicked") is True, confirmed

        success = wait_for_state(client, page, _SUCCESS_STATE_JS, timeout_sec=45.0)
        assert success.get("ready") is True, json.dumps(success, ensure_ascii=False)

    restored = http_json(
        "GET",
        f"{api_url}/api/v1/files/revert/changes/{chat_id}/{message_id}",
        expected_statuses=frozenset({200}),
    )
    assert restored == []

    assert Path(file_path).read_text(encoding="utf-8") == "revert fixture before\n"


_EMPTY_TOAST_READY_JS = """(() => {
  const toastNodes = Array.from(document.querySelectorAll('[data-sonner-toast]'));
  const toastText = toastNodes.map((node) => node.textContent || '').join(' ');
  const bodyText = document.body?.innerText || '';
  const merged = `${toastText} ${bodyText}`;
  const hasEmptyToast = /No file changes for this message|本条消息无文件变更/i.test(merged);
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  return { ready: hasEmptyToast && !popover, sample: merged.slice(0, 300) };
})()"""


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_revert_files_empty_changes_shows_toast_not_popover() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_revert_fixture(api_url, variant="empty")
    chat_id = str(seeded["chat_id"])

    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg }};
            }})()""",
            timeout_sec=90.0,
        )

        clicked = client.evaluate(page, _CLICK_UNDO_JS, timeout_sec=10.0)
        assert isinstance(clicked, dict) and clicked.get("clicked") is True, clicked

        toast_state = wait_for_state(client, page, _EMPTY_TOAST_READY_JS, timeout_sec=30.0)
        assert toast_state.get("ready") is True, json.dumps(toast_state, ensure_ascii=False)

