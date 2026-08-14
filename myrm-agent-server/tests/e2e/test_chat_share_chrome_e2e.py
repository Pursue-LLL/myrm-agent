"""Real Chrome E2E: chat share lifecycle through the WebUI.

A user's full share flow, end to end, without mocks:
  T1 - Seed a renderable chat (user + assistant exchange) and open it in the WebUI.
  T2 - Sidebar row -> More menu -> Share opens ShareConversationDialog.
  T3 - Create Share Link -> the dialog shows the live share URL + expires date;
       the public page behind that URL serves the conversation content.
  T4 - Close + reopen the dialog -> the status endpoint rebuilds the unprotected
       link deterministically, so the same share URL is shown again.
  T5 - Revoke Link -> the dialog shows the revoked status + a fresh create form;
       the revoked public URL answers 404 ("Link Revoked").
  T6 - Recreate -> a brand-new URL is issued and serves the conversation again
       (a revoked link is never resurrected by a recreate).

The public pages are also rendered in the real browser (navigating the owned
page to the share URL and back), so the served HTML is verified the way an end
user sees it — not only through the HTTP client.

Prerequisite:
  ./myrm isolate <id> ready --chrome   (workspace backend epoch on a PRIVATE
  runtime — the shared :8080 is pinned to a deployed epoch that predates the
  share-status endpoint, so this test cannot run SHARED)
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from tests.support.chrome_mcp_e2e import (
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

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


def _open_share_dialog_js(chat_id: str) -> str:
    """Open the chat row More menu and click the Share item (idempotent)."""
    return f"""(() => {{
  const dialog = document.querySelector('[role="dialog"]');
  if (dialog && /Share Conversation|分享对话/.test(dialog.textContent || '')) {{
    return {{ ready: true, alreadyOpen: true }};
  }}
  const href = {json.dumps(f"/{chat_id}")};
  const row = document.querySelector(`a[href="${{href}}"]`);
  if (!row) return {{ ready: false, reason: 'no-row', href }};
  const more = Array.from(row.querySelectorAll('button')).find(
    (b) => !(b.textContent || '').trim(),
  );
  if (!more) return {{ ready: false, reason: 'no-more-btn' }};
  more.dispatchEvent(new PointerEvent('pointerdown', {{
    bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', button: 0,
  }}));
  more.click();
  return new Promise((resolve) => setTimeout(() => {{
    const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
    const share = items.find((el) => {{
      const text = (el.textContent || '').trim();
      return text === 'Share' || text === '分享';
    }});
    if (!share) {{
      return resolve({{
        ready: false, reason: 'no-share-item',
        items: items.map((i) => (i.textContent || '').trim()),
      }});
    }}
    share.click();
    setTimeout(() => {{
      const dialog2 = document.querySelector('[role="dialog"]');
      const open = !!(
        dialog2 && /Share Conversation|分享对话/.test(dialog2.textContent || '')
      );
      resolve({{
        ready: open, opened: open,
        title: dialog2 ? (dialog2.textContent || '').slice(0, 120) : null,
      }});
    }}, 250);
  }}, 400));
}})()"""


_CREATE_FORM_READY_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { ready: false, reason: 'no-dialog' };
  const text = (dialog.textContent || '');
  const createBtn = Array.from(dialog.querySelectorAll('button')).some((b) => {
    const t = (b.textContent || '').trim();
    return (t === 'Create Share Link' || t === '创建分享链接') && !b.disabled;
  });
  return { ready: createBtn, loading: /Creating|创建中/.test(text) };
})()"""


_CLICK_CREATE_LINK_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { ok: false, reason: 'no-dialog' };
  const btn = Array.from(dialog.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return (t === 'Create Share Link' || t === '创建分享链接')
      && !b.disabled && b.offsetParent !== null;
  });
  if (!btn) return { ok: false, reason: 'no-create-btn' };
  btn.click();
  return { ok: true };
})()"""


_SHARE_URL_READY_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { ready: false, reason: 'no-dialog' };
  const input = dialog.querySelector('input[readonly]');
  const url = input ? (input.value || '').trim() : '';
  if (!/^https?:\\/\\//.test(url)) return { ready: false, reason: 'no-url', value: url.slice(0, 80) };
  const text = dialog.textContent || '';
  return {
    ready: true,
    url,
    expiresShown: /Expires|有效期|到期/.test(text),
    hasRevokeBtn: /Revoke Link|撤回链接/.test(text),
    dialogText: text.slice(0, 300),
  };
})()"""


_CLICK_REVOKE_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { ok: false, reason: 'no-dialog' };
  const btn = Array.from(dialog.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return (t === 'Revoke Link' || t === '撤回链接') && !b.disabled && b.offsetParent !== null;
  });
  if (!btn) return { ok: false, reason: 'no-revoke-btn' };
  btn.click();
  return { ok: true };
})()"""


_REVOKED_READY_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { ready: false, reason: 'no-dialog' };
  const text = (dialog.textContent || '');
  const revoked = /This share link has been revoked|该分享链接已撤回/.test(text);
  const createBtn = Array.from(dialog.querySelectorAll('button')).some((b) => {
    const t = (b.textContent || '').trim();
    return (t === 'Create Share Link' || t === '创建分享链接') && !b.disabled;
  });
  return { ready: revoked && createBtn, revoked, text: text.slice(0, 200) };
})()"""


_DIALOG_CLOSED_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  const text = dialog ? (dialog.textContent || '') : '';
  return { ready: !dialog || !/Share Conversation|分享对话/.test(text) };
})()"""


_DIALOG_PROTECTED_STATUS_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { ready: false, reason: 'no-dialog' };
  const text = (dialog.textContent || '');
  const status = /A password-protected share link is active|密码保护的分享链接生效中/.test(text);
  const hasUrlInput = !!dialog.querySelector('input[readonly]');
  const hasRevokeBtn = Array.from(dialog.querySelectorAll('button')).some((b) => {
    const t = (b.textContent || '').trim();
    return (t === 'Revoke Link' || t === '撤回链接') && !b.disabled;
  });
  return { ready: status && hasRevokeBtn, status, hasUrlInput, hasRevokeBtn };
})()"""


def _fill_share_password_js(password: str) -> str:
    """Set the dialog password field via the React input value setter."""
    return f"""(() => {{
  const input = document.querySelector('[role="dialog"] input[type="password"]');
  if (!input) return {{ ok: false, reason: 'no-password-input' }};
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(input, {json.dumps(password)});
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return {{ ok: true, value: input.value }};
}})()"""


_GATE_READY_JS = """(() => ({
  ready: !!document.querySelector('input[name="p"]')
    && !!Array.from(document.querySelectorAll('button')).some(
      (b) => (b.textContent || '').trim() === 'Unlock',
    ),
  title: document.title,
  body: (document.body?.innerText || '').slice(0, 160),
}))()"""


_GATE_WRONG_PASSWORD_JS = """(() => ({
  ready: /Incorrect password/.test(document.body?.innerText || ''),
  body: (document.body?.innerText || '').slice(0, 200),
}))()"""


def _public_content_ready_js(needle: str) -> str:
    """True when the public page rendered the shared conversation text."""
    return f"""(() => {{
  const text = document.body?.innerText || '';
  return {{ ready: text.includes({json.dumps(needle)}), bodyLen: text.length, body: text.slice(0, 200) }};
}})()"""


def _public_status_page_js(title: str) -> str:
    """True when the public page rendered the given status page (e.g. Link Revoked)."""
    return f"""(() => {{
  const text = document.body?.innerText || '';
  return {{ ready: text.includes({json.dumps(title)}), body: text.slice(0, 200) }};
}})()"""


def _submit_gate_password_js(password: str) -> str:
    """Fill and submit the password gate form (real browser POST + 303 follow)."""
    return f"""(() => {{
  const input = document.querySelector('input[name="p"]');
  const form = document.querySelector('form');
  if (!input || !form) return {{ ok: false, reason: 'no-gate-form' }};
  input.value = {json.dumps(password)};
  form.submit();
  return {{ ok: true }};
}})()"""


def _poll_js(
    client,
    page,
    expression: str,
    *,
    timeout_sec: float = 25.0,
) -> dict[str, object]:
    """Poll a probe until ready, tolerating navigation in flight.

    Deliberately avoids ``wait_for_state``: public share pages live outside the
    UI origin, and its blank/heal heuristics would re-navigate to the app shell.
    """
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        try:
            raw = client.evaluate(
                page,
                expression,
                timeout_sec=min(15.0, max(5.0, deadline - time.monotonic())),
            )
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            last = {"err": str(exc)}
            time.sleep(0.25)
            continue
        if isinstance(raw, dict):
            last = raw
            if raw.get("ready") is True:
                return raw
        time.sleep(0.25)
    raise AssertionError(f"browser probe timed out: {last}")


def _seed_chat_share_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-chat-share-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2eshare")
    return {
        "chat_id": chat_id,
        "user_text": str(seeded["user_text"]),
        "assistant_text": str(seeded["assistant_text"]),
        "ui_path": str(seeded["ui_path"]),
    }


def _fetch_public_page(share_url: str, api_url: str) -> tuple[int, str]:
    """GET the public share page through the loopback backend (HTML, no JSON)."""
    from urllib.parse import urlparse

    path = urlparse(share_url).path
    api_base = api_url.rstrip("/")
    target = f"{api_base}{path}"
    host = urlparse(target).hostname
    if host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        raise AssertionError(f"refusing non-loopback share URL: {target}")
    request = urllib.request.Request(  # noqa: S310 - validated loopback
        target, headers={"Accept": "text/html"}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chat_share_lifecycle_via_ui() -> None:
    """Create, reopen, revoke, and recreate a chat share link in the real WebUI."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_chat_share_fixture(api_url)
    chat_id = seeded["chat_id"]
    chat_url = f"{ui_url}{seeded['ui_path']}"

    warm_ui_route("/", timeout_sec=45.0)
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        dismiss_blocking_modals(client, page)

        # T2: open the share dialog from the sidebar row menu.
        opened = wait_for_state(
            client,
            page,
            _open_share_dialog_js(chat_id),
            timeout_sec=45.0,
            page_url=chat_url,
        )
        assert opened.get("ready") is True, json.dumps(opened, indent=2)

        # T3: create the share link, then confirm the dialog shows the live URL.
        form = wait_for_state(client, page, _CREATE_FORM_READY_JS, timeout_sec=20.0, page_url=chat_url)
        assert form.get("ready") is True, json.dumps(form, indent=2)

        clicked = client.evaluate(page, _CLICK_CREATE_LINK_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        url_state = wait_for_state(client, page, _SHARE_URL_READY_JS, timeout_sec=30.0, page_url=chat_url)
        assert url_state.get("ready") is True, json.dumps(url_state, indent=2)
        assert url_state.get("expiresShown") is True, url_state
        assert url_state.get("hasRevokeBtn") is True, url_state
        share_url = str(url_state["url"])

        # Real browser: render the public page exactly as an end user would, then
        # navigate back to the app so the dialog flow continues on the UI origin.
        client.navigate(page, share_url, timeout_ms=90_000)
        public_state = _poll_js(
            client,
            page,
            _public_content_ready_js(seeded["assistant_text"]),
            timeout_sec=30.0,
        )
        assert public_state.get("ready") is True, public_state
        client.navigate(page, chat_url, timeout_ms=90_000)
        wait_for_react_e2e_bridge(client, page, timeout_sec=60.0, page_url=chat_url)

        status, body = _fetch_public_page(share_url, api_url)
        assert status == 200, f"public page status={status} body={body[:300]}"
        assert seeded["assistant_text"] in body, body[:800]

        # T4: close the dialog and reopen it — the status endpoint rebuilds the
        # unprotected link so the same URL must be shown again.
        client.press_key(page, "Escape")
        closed = wait_for_state(client, page, _DIALOG_CLOSED_JS, timeout_sec=15.0, page_url=chat_url)
        assert closed.get("ready") is True, closed

        reopened = wait_for_state(
            client,
            page,
            _open_share_dialog_js(chat_id),
            timeout_sec=45.0,
            page_url=chat_url,
        )
        assert reopened.get("ready") is True, json.dumps(reopened, indent=2)

        reopen_state = wait_for_state(client, page, _SHARE_URL_READY_JS, timeout_sec=30.0, page_url=chat_url)
        assert reopen_state.get("ready") is True, json.dumps(reopen_state, indent=2)
        assert reopen_state["url"] == share_url, (
            f"reopen must rebuild the same unprotected link (expected={share_url} got={reopen_state['url']})"
        )

        # T5: revoke — dialog shows revoked status, public page answers 404.
        revoked_click = client.evaluate(page, _CLICK_REVOKE_JS, timeout_sec=15.0)
        assert isinstance(revoked_click, dict) and revoked_click.get("ok") is True, revoked_click
        revoked_state = wait_for_state(client, page, _REVOKED_READY_JS, timeout_sec=30.0, page_url=chat_url)
        assert revoked_state.get("ready") is True, json.dumps(revoked_state, indent=2)

        status, body = _fetch_public_page(share_url, api_url)
        assert status == 404, f"revoked public page status={status} body={body[:300]}"
        assert "Link Revoked" in body, body[:800]

        # Real browser: the revoked link answers the browser with the status page.
        client.navigate(page, share_url, timeout_ms=90_000)
        revoked_page = _poll_js(
            client,
            page,
            _public_status_page_js("Link Revoked"),
            timeout_sec=30.0,
        )
        assert revoked_page.get("ready") is True, revoked_page
        client.navigate(page, chat_url, timeout_ms=90_000)
        wait_for_react_e2e_bridge(client, page, timeout_sec=60.0, page_url=chat_url)

        # T6: recreate issues a brand-new URL that serves the conversation again
        # while the old (revoked) link stays dead.
        recreated = client.evaluate(page, _CLICK_CREATE_LINK_JS, timeout_sec=15.0)
        assert isinstance(recreated, dict) and recreated.get("ok") is True, recreated
        recreate_state = wait_for_state(client, page, _SHARE_URL_READY_JS, timeout_sec=30.0, page_url=chat_url)
        assert recreate_state.get("ready") is True, json.dumps(recreate_state, indent=2)
        new_url = str(recreate_state["url"])
        assert new_url != share_url, "a recreated link must not reuse the revoked token"

        status, body = _fetch_public_page(new_url, api_url)
        assert status == 200, f"recreated public page status={status} body={body[:300]}"
        assert seeded["assistant_text"] in body, body[:800]


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chat_share_password_protected_via_ui() -> None:
    """Password-protected share: create in the dialog, gate in the real browser, revoke.

    A password-protected link cannot be rebuilt from the status endpoint (the
    password is never stored), so the dialog must switch to the protected-status
    view on reopen instead of showing a URL; the public link opens a password
    gate that unlocks only with the correct password.
    """
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_chat_share_fixture(api_url)
    chat_id = seeded["chat_id"]
    chat_url = f"{ui_url}{seeded['ui_path']}"

    warm_ui_route("/", timeout_sec=45.0)
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        dismiss_blocking_modals(client, page)

        opened = wait_for_state(
            client,
            page,
            _open_share_dialog_js(chat_id),
            timeout_sec=45.0,
            page_url=chat_url,
        )
        assert opened.get("ready") is True, json.dumps(opened, indent=2)

        form = wait_for_state(client, page, _CREATE_FORM_READY_JS, timeout_sec=20.0, page_url=chat_url)
        assert form.get("ready") is True, json.dumps(form, indent=2)

        filled = client.evaluate(page, _fill_share_password_js("s3cret"), timeout_sec=15.0)
        assert isinstance(filled, dict) and filled.get("ok") is True, filled

        clicked = client.evaluate(page, _CLICK_CREATE_LINK_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        url_state = wait_for_state(client, page, _SHARE_URL_READY_JS, timeout_sec=30.0, page_url=chat_url)
        assert url_state.get("ready") is True, json.dumps(url_state, indent=2)
        share_url = str(url_state["url"])

        # Real browser: the protected link opens a password gate, not the content.
        client.navigate(page, share_url, timeout_ms=90_000)
        gate = _poll_js(client, page, _GATE_READY_JS, timeout_sec=30.0)
        assert gate.get("ready") is True, gate

        wrong = client.evaluate(page, _submit_gate_password_js("nope"), timeout_sec=15.0)
        assert isinstance(wrong, dict) and wrong.get("ok") is True, wrong
        err = _poll_js(client, page, _GATE_WRONG_PASSWORD_JS, timeout_sec=20.0)
        assert err.get("ready") is True, err

        correct = client.evaluate(page, _submit_gate_password_js("s3cret"), timeout_sec=15.0)
        assert isinstance(correct, dict) and correct.get("ok") is True, correct
        content = _poll_js(
            client,
            page,
            _public_content_ready_js(seeded["assistant_text"]),
            timeout_sec=30.0,
        )
        assert content.get("ready") is True, content

        # Back in the UI: reopening shows the protected status — no URL to rebuild.
        client.navigate(page, chat_url, timeout_ms=90_000)
        wait_for_react_e2e_bridge(client, page, timeout_sec=60.0, page_url=chat_url)
        reopened = wait_for_state(
            client,
            page,
            _open_share_dialog_js(chat_id),
            timeout_sec=45.0,
            page_url=chat_url,
        )
        assert reopened.get("ready") is True, json.dumps(reopened, indent=2)

        protected = wait_for_state(client, page, _DIALOG_PROTECTED_STATUS_JS, timeout_sec=30.0, page_url=chat_url)
        assert protected.get("ready") is True, json.dumps(protected, indent=2)
        assert protected.get("hasUrlInput") is False, protected

        # Revoke from the dialog; the protected link answers 404 afterwards.
        revoked_click = client.evaluate(page, _CLICK_REVOKE_JS, timeout_sec=15.0)
        assert isinstance(revoked_click, dict) and revoked_click.get("ok") is True, revoked_click
        revoked_state = wait_for_state(client, page, _REVOKED_READY_JS, timeout_sec=30.0, page_url=chat_url)
        assert revoked_state.get("ready") is True, json.dumps(revoked_state, indent=2)

        status, body = _fetch_public_page(share_url, api_url)
        assert status == 404, f"revoked protected public page status={status} body={body[:300]}"
        assert "Link Revoked" in body, body[:800]
