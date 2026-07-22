"""Real Chrome MCP E2E for RevertFiles: Undo → diff popover → Confirm → resync."""

from __future__ import annotations

import json
import time
import urllib.error
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_FIXTURE_ANSWER = "Revert E2E fixture answer with file change."

_SCOPED_REVERT_BTN_HELPER = """
  const findFixtureRevertButton = (answerText) => {
    const store = window.__myrmChatStore?.getState?.();
    const msg = (store?.messages || []).find(
      (item) => item.role === 'assistant' && (item.content || '').includes(answerText),
    );
    if (!msg) return { msg: null, btn: null };
    const markdown = document.querySelector(`[data-message-id="${msg.messageId}"]`);
    const scope = markdown?.closest('.flex.flex-col.space-y-2') ?? markdown?.parentElement;
    const btn = scope
      ? Array.from(scope.querySelectorAll('button[title]')).find((candidate) => {
          const title = candidate.getAttribute('title') || '';
          return /Undo file changes|撤销文件变更/i.test(title);
        })
      : null;
    return { msg, btn };
  };
"""

_UNDO_BUTTON_READY_JS = f"""(() => {{
  {_SCOPED_REVERT_BTN_HELPER}
  const {{ btn }} = findFixtureRevertButton({json.dumps(_FIXTURE_ANSWER)});
  if (!btn) return {{ ready: false }};
  return {{ ready: true, title: btn.getAttribute('title') || null }};
}})()"""


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
  return {
    ready: window.__MYRM_REVERT_RESYNC__ === true,
    resyncSeen: window.__MYRM_REVERT_RESYNC__ === true,
  };
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
    let last = {{ ok: false, status: 0, chatId, messageId: msg.messageId, body: '' }};
    for (let attempt = 0; attempt < 12; attempt += 1) {{
      const res = await fetch(`/api/v1/files/revert/changes/${{chatId}}/${{msg.messageId}}`);
      const body = await res.text();
      last = {{
        ok: res.ok && body.startsWith('[') && body.includes('revert_e2e_fixture.txt'),
        status: res.status,
        chatId,
        messageId: msg.messageId,
        body: body.slice(0, 300),
      }};
      if (last.ok) return last;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }}
    return last;
  }})();
}})()"""


def _http_json_with_retry(
    method: str,
    url: str,
    *,
    expected_statuses: frozenset[int] = frozenset({200, 201, 204}),
    timeout_sec: float = 30.0,
) -> object:
    deadline = time.monotonic() + timeout_sec
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            return http_json(method, url, expected_statuses=expected_statuses)
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise AssertionError(f"HTTP {method} {url} failed after {timeout_sec}s: {last_error}")


def _ensure_revert_changes_ready(
    api_url: str,
    chat_id: str,
    message_id: str,
    *,
    min_changes: int,
    timeout_sec: float = 45.0,
) -> None:
    """Poll :8080 before Chrome fetch; attach stack may restart backend briefly."""
    deadline = time.monotonic() + timeout_sec
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            data = http_json(
                "GET",
                f"{api_url}/api/v1/files/revert/changes/{chat_id}/{message_id}",
            )
            if isinstance(data, list) and len(data) >= min_changes:
                return
            last_error = f"unexpected payload: {data!r}"
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.3)
    raise AssertionError(
        f"revert/changes not ready chat={chat_id} message={message_id} "
        f"min_changes={min_changes}: {last_error}"
    )


def _wait_revert_changes_cleared(
    api_url: str,
    chat_id: str,
    message_id: str,
    *,
    timeout_sec: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last: object = "timeout"
    while time.monotonic() < deadline:
        last = _http_json_with_retry(
            "GET",
            f"{api_url}/api/v1/files/revert/changes/{chat_id}/{message_id}",
            expected_statuses=frozenset({200}),
            timeout_sec=5.0,
        )
        if last == []:
            return
        time.sleep(0.5)
    raise AssertionError(
        f"revert/changes still present chat={chat_id} message={message_id}: {last!r}"
    )


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


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_revert_files_undo_diff_confirm_flow() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_revert_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    message_id = str(seeded["message_id"])
    file_path = str(seeded["file_path"])
    _ensure_revert_changes_ready(api_url, chat_id, message_id, min_changes=1)

    prepare_e2e_ui_session(api_url)
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

        dismiss_blocking_modals(client, page)

        fetch_probe = client.evaluate(page, _PROBE_REVERT_FETCH_JS, timeout_sec=30.0)
        assert isinstance(fetch_probe, dict) and fetch_probe.get("ok") is True, json.dumps(
            fetch_probe,
            ensure_ascii=False,
        )

        button = wait_for_state(client, page, _UNDO_BUTTON_READY_JS, timeout_sec=30.0)
        assert button.get("ready") is True, json.dumps(button, ensure_ascii=False)

        popover = client.evaluate(page, _CLICK_UNDO_AND_WAIT_POPOVER_JS, timeout_sec=70.0)
        assert isinstance(popover, dict) and popover.get("ready") is True, json.dumps(
            popover,
            ensure_ascii=False,
        )

        confirmed = client.evaluate(page, _CLICK_CONFIRM_JS, timeout_sec=10.0)
        assert isinstance(confirmed, dict) and confirmed.get("clicked") is True, confirmed

        success = wait_for_state(client, page, _SUCCESS_STATE_JS, timeout_sec=60.0)
        assert success.get("ready") is True, json.dumps(success, ensure_ascii=False)

    _wait_revert_changes_cleared(api_url, chat_id, message_id)

    assert Path(file_path).read_text(encoding="utf-8") == "revert fixture before\n"


_CLICK_UNDO_AND_WAIT_POPOVER_JS = f"""(() => {{
  {_SCOPED_REVERT_BTN_HELPER}
  return (async () => {{
    const {{ btn }} = findFixtureRevertButton({json.dumps(_FIXTURE_ANSWER)});
    if (!btn) return {{ ready: false, err: 'revert-button-missing' }};
    btn.click();
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) {{
      const popover = document.querySelector('[data-radix-popper-content-wrapper]');
      const text = popover?.textContent || '';
      const hasConfirm = /Undo these changes\\?|撤销这些变更？/i.test(text);
      const hasFile = /revert_e2e_fixture\\.txt/i.test(text);
      const hasAction = /Confirm revert|确认撤销/i.test(text);
      if (popover && hasConfirm && hasFile && hasAction) {{
        return {{ ready: true, sample: text.slice(0, 400) }};
      }}
      await new Promise((resolve) => setTimeout(resolve, 300));
    }}
    const fallback = document.querySelector('[data-radix-popper-content-wrapper]')?.textContent
      || document.body?.innerText
      || '';
    return {{ ready: false, sample: fallback.slice(0, 400) }};
  }})();
}})()"""

_PROBE_REVERT_EMPTY_FETCH_JS = f"""(() => {{
  return (async () => {{
    const chatId = location.pathname.replace(/^\\//, '');
    const store = window.__myrmChatStore?.getState?.();
    const msg = (store?.messages || []).find(
      (item) => item.role === 'assistant' && (item.content || '').includes({json.dumps(_FIXTURE_ANSWER)}),
    );
    if (!msg) {{
      return {{ ok: false, err: 'fixture-message-missing', chatId }};
    }}
    const res = await fetch(`/api/v1/files/revert/changes/${{chatId}}/${{msg.messageId}}`);
    const body = await res.text();
    return {{
      ok: res.ok && body === '[]',
      status: res.status,
      chatId,
      messageId: msg.messageId,
      body: body.slice(0, 120),
    }};
  }})();
}})()"""

_CLICK_UNDO_AND_WAIT_EMPTY_TOAST_JS = f"""(() => {{
  {_SCOPED_REVERT_BTN_HELPER}
  return (async () => {{
    const {{ btn }} = findFixtureRevertButton({json.dumps(_FIXTURE_ANSWER)});
    if (!btn) return {{ ready: false, err: 'revert-button-missing' }};
    btn.click();
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {{
      const toastNodes = Array.from(
        document.querySelectorAll('[data-sonner-toast], [data-sonner-toaster] [data-sonner-toast]'),
      );
      const toastText = toastNodes.map((node) => node.textContent || '').join(' ');
      const bodyText = document.body?.innerText || '';
      const merged = `${{toastText}} ${{bodyText}}`;
      const hasEmptyToast = /No file changes for this message|本条消息无文件变更/i.test(merged);
      const popover = document.querySelector('[data-radix-popper-content-wrapper]');
      if (hasEmptyToast && !popover) {{
        return {{ ready: true, sample: merged.slice(0, 300) }};
      }}
      await new Promise((resolve) => setTimeout(resolve, 200));
    }}
    const fallback = document.body?.innerText || '';
    return {{ ready: false, sample: fallback.slice(0, 400) }};
  }})();
}})()"""


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_revert_files_empty_changes_shows_toast_not_popover() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_revert_fixture(api_url, variant="empty")
    chat_id = str(seeded["chat_id"])
    message_id = str(seeded["message_id"])
    _ensure_revert_changes_ready(api_url, chat_id, message_id, min_changes=0)

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        message_ready = wait_for_state(
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
        assert message_ready.get("ready") is True, json.dumps(message_ready, ensure_ascii=False)

        dismiss_blocking_modals(client, page)

        empty_probe = client.evaluate(page, _PROBE_REVERT_EMPTY_FETCH_JS, timeout_sec=30.0)
        assert isinstance(empty_probe, dict) and empty_probe.get("ok") is True, json.dumps(
            empty_probe,
            ensure_ascii=False,
        )

        undo_ready = wait_for_state(client, page, _UNDO_BUTTON_READY_JS, timeout_sec=30.0)
        assert undo_ready.get("ready") is True, json.dumps(undo_ready, ensure_ascii=False)

        toast_state = client.evaluate(page, _CLICK_UNDO_AND_WAIT_EMPTY_TOAST_JS, timeout_sec=60.0)
        assert isinstance(toast_state, dict) and toast_state.get("ready") is True, json.dumps(
            toast_state,
            ensure_ascii=False,
        )


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_revert_files_undo_works_after_page_reload() -> None:
    """Hydrate from disk: full page reload clears in-memory store; Undo must still work."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_revert_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    message_id = str(seeded["message_id"])
    file_path = str(seeded["file_path"])
    _ensure_revert_changes_ready(api_url, chat_id, message_id, min_changes=1)

    prepare_e2e_ui_session(api_url)
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
              return {{ ready: !!msg }};
            }})()""",
            timeout_sec=90.0,
        )
        assert probe.get("ready") is True, json.dumps(probe, ensure_ascii=False)

        client.navigate(page, f"{ui_url}/{chat_id}", timeout_ms=120_000)
        client.evaluate(page, _HOOK_RESYNC_JS, timeout_sec=10.0)

        reloaded = wait_for_state(
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
        assert reloaded.get("ready") is True, json.dumps(reloaded, ensure_ascii=False)

        dismiss_blocking_modals(client, page)

        fetch_probe = client.evaluate(page, _PROBE_REVERT_FETCH_JS, timeout_sec=30.0)
        assert isinstance(fetch_probe, dict) and fetch_probe.get("ok") is True, json.dumps(
            fetch_probe,
            ensure_ascii=False,
        )

        popover = client.evaluate(page, _CLICK_UNDO_AND_WAIT_POPOVER_JS, timeout_sec=70.0)
        assert isinstance(popover, dict) and popover.get("ready") is True, json.dumps(
            popover,
            ensure_ascii=False,
        )

        confirmed = client.evaluate(page, _CLICK_CONFIRM_JS, timeout_sec=10.0)
        assert isinstance(confirmed, dict) and confirmed.get("clicked") is True, confirmed

        success = wait_for_state(client, page, _SUCCESS_STATE_JS, timeout_sec=60.0)
        assert success.get("ready") is True, json.dumps(success, ensure_ascii=False)

    _wait_revert_changes_cleared(api_url, chat_id, message_id)
    assert Path(file_path).read_text(encoding="utf-8") == "revert fixture before\n"
