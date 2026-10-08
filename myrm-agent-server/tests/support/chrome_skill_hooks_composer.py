"""The browser side of the skill-hooks Chrome E2E: everything a user does in the composer.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers)
- tests.support.chrome_skill_hooks_live_e2e (POS: SkillChat probe)
- tests.support.chrome_skill_hooks_observe (POS: persisted-message wait)

[OUTPUT]
- drive_chat_turn(): slash-pick the skill chip, optionally attach a file, type the request, press send
- TextAttachment: a small text file picked through the composer's real file input
- wait_for_approval_card() / click_approve(): the tool-approval card of a HITL-parked run
- TRANSCRIPT_CHIP_JS: the sent message renders the skill as a chip, not as the raw ``[use skill]`` text

[POS]
Shared by tests/e2e/test_skill_hooks_live_chrome_e2e.py. Nothing here talks to the product API: the composer, not a
test shortcut, builds the wire message, so the explicit-invocation tag takes the same path as for a real user.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.chrome_skill_hooks_live_e2e import SkillChat
from tests.support.chrome_skill_hooks_observe import wait_user_message_persisted


@dataclass(frozen=True)
class TextAttachment:
    """A text file the user attaches; a message with an attachment reaches the agent as content blocks."""

    name: str
    text: str


# --- real WebUI driving ----------------------------------------------------------------------------

_ATTACH_CHAT_PROBE = """(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const store = window.__myrmChatStore?.getState?.();
  const attached =
    store?.chatId === {chat_id_json}
    && Boolean(store?.isMessagesLoaded)
    && !Boolean(store?.loadError)
    && !Boolean(store?.notFound);
  if (attached) return {{ ready: true, chatId: store?.chatId ?? null }};
  if (bridge?.attachToChat && !window.__MYRM_E2E_ATTACHING__) {{
    window.__MYRM_E2E_ATTACHING__ = true;
    bridge.attachToChat({chat_id_json}).catch(() => {{}}).finally(() => {{
      window.__MYRM_E2E_ATTACHING__ = false;
    }});
  }}
  return {{ ready: false, chatId: store?.chatId ?? null, err: !bridge ? 'no-bridge' : null }};
}})()"""

_COMPOSER_READY_JS = """(() => ({ ready: !!document.querySelector('[data-chat-input]') }))()"""

# Adopted local skills live in the user's skill catalog (the agent's own skill list stays empty), so the
# slash palette needs the catalog fetched, exactly like opening the skill picker does.
_PREFETCH_SKILL_CATALOG_JS = """(async () => {
  await window.__MYRM_E2E_CHAT__?.prefetchSlashSkillCatalog?.();
  return { ok: true };
})()"""

_TYPE_JS = """((text) => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false, err: 'input-not-found' };
  el.focus();
  // React-controlled textarea: native value setter + input event, as a real keystroke would.
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  setter.call(el, text);
  el.setSelectionRange(el.value.length, el.value.length);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, value: el.value };
})"""

# One poll step = "chip present? done : click the palette entry if it is on screen right now". The palette
# list re-renders while the skill catalog refreshes, so finding the entry and clicking it in two separate
# browser round-trips can lose the entry in between.
_PICK_SKILL_CHIP_JS = """((needle) => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const pending = Array.isArray(snap.pendingSkillNames) ? snap.pendingSkillNames : [];
  if (document.querySelector('[data-testid="skill-activation-chips"]') && pending.length > 0) {
    return { ready: true, pendingSkillNames: pending };
  }
  const palette = document.querySelector('[data-testid="slash-command-palette"]');
  const items = palette ? Array.from(palette.querySelectorAll('[cmdk-item], [role="option"]')) : [];
  const target = items.find((el) => (el.textContent || '').toLowerCase().includes(needle));
  if (target) target.click();
  return { ready: false, paletteEntries: items.slice(0, 6).map((el) => (el.textContent || '').slice(0, 60)) };
})"""

# The composer's own file input, driven like the browser does when a user picks a file in the dialog.
_ATTACH_TEXT_FILE_JS = """((spec) => {
  const input = document.querySelector('input[type="file"]');
  if (!input) return { ok: false, err: 'file-input-missing' };
  const transfer = new DataTransfer();
  transfer.items.add(new File([spec.text], spec.name, { type: 'text/plain' }));
  input.files = transfer.files;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true };
})"""

# The staged file shows up as a pill labelled with its name; the pill spins until the upload finished.
_ATTACHMENT_READY_JS = """((name) => {
  const labels = Array.from(document.querySelectorAll('p[title]'));
  const label = labels.find((el) => el.getAttribute('title') === name);
  const pill = label ? label.closest('div.rounded-full') : null;
  const uploading = Boolean(pill && pill.querySelector('.animate-spin'));
  return {
    ready: Boolean(label) && !uploading,
    staged: Boolean(label),
    uploading,
    titles: labels.slice(0, 8).map((el) => el.getAttribute('title')),
    spinners: document.querySelectorAll('.animate-spin').length,
  };
})"""

_USE_AGENT_MODE_JS = """(() => {
  window.__MYRM_E2E_CHAT__?.setActionMode?.('agent');
  return { ok: true };
})()"""

# A typed URL makes the composer ask whether to attach it with an @ mention; "No" keeps it as plain text.
_DISMISS_LINK_PROMPT_JS = """(() => {
  const checkbox = document.querySelector('#dontRemindAgain');
  if (!checkbox) return { ready: false };
  const dialog = checkbox.closest('[role="dialog"]');
  const keepAsText = dialog ? dialog.querySelector('button.rounded-full') : null;
  if (!keepAsText) return { ready: false };
  keepAsText.click();
  return { ready: true };
})()"""

# ``wire`` is what the composer will hand to the chat store: the typed text behind the ``[use skill]`` chip.
_SEND_READY_JS = """((text) => {
  const send = document.querySelector('button.message-send-btn');
  const wire = window.__MYRM_E2E_CHAT__?.peekOutboundUserMessage?.() ?? '';
  const linkPromptOpen = Boolean(document.querySelector('#dontRemindAgain'));
  return { ready: Boolean(send) && !send.disabled && !linkPromptOpen && wire.includes(text), wire };
})"""

# Pass-through trace of every request the page makes after the click, so a message the server never stored
# can be told apart from one the page never sent.
_CLICK_SEND_JS = """(() => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const send = document.querySelector('button.message-send-btn');
  if (!send || send.disabled) return { ok: false, err: 'send-button-unavailable' };
  if (!window.__MYRM_SEND_TRACE__) {
    const trace = (window.__MYRM_SEND_TRACE__ = []);
    const original = window.fetch;
    window.fetch = async (...args) => {
      const target = args[0];
      const record = { url: String(target?.url ?? target).slice(-140), method: String(args[1]?.method ?? target?.method ?? 'GET') };
      trace.push(record);
      try {
        const response = await original.apply(window, args);
        record.status = response.status;
        return response;
      } catch (error) {
        record.error = String(error).slice(0, 160);
        throw error;
      }
    };
    window.addEventListener('unhandledrejection', (event) => trace.push({ rejection: String(event.reason).slice(0, 200) }));
    window.addEventListener('error', (event) => trace.push({ error: String(event.message).slice(0, 200) }));
  }
  send.click();
  return { ok: true };
})()"""

# What the page itself believes happened to the message that was just sent (for a failed persistence wait).
_SEND_DIAGNOSTICS_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const send = document.querySelector('button.message-send-btn');
  const notices = Array.from(document.querySelectorAll('[role="alert"], [data-sonner-toast]'))
    .map((el) => (el.textContent || '').trim().slice(0, 160))
    .slice(0, 4);
  return {
    apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
    runtimeId: window.__MYRM_E2E_RUNTIME__?.runtimeId ?? null,
    directSse: Boolean(window.__MYRM_E2E_DIRECT_SSE__),
    chatId: snap.chatId ?? null,
    userCount: snap.userCount ?? null,
    isStreaming: snap.isStreaming ?? null,
    sendButtonDisabled: send ? send.disabled : null,
    notices,
    requests: (window.__MYRM_SEND_TRACE__ ?? []).slice(-12),
  };
})()"""

TRANSCRIPT_CHIP_JS = """(() => {
  const chips = document.querySelector('[data-testid="skill-activation-chips"]');
  const bubble = document.querySelector('[data-message-id]');
  const text = (bubble?.textContent || '').trim();
  return { ready: Boolean(chips) && Boolean(text), hasRawUsePrefix: /\\[use\\s/i.test(text), text };
})()"""

_APPROVAL_VISIBLE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.toolApprovalSnapshot?.() ?? {};
  const queueLen = Number(snap.queueLen ?? 0);
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  const text = document.body?.innerText || '';
  return { ready: hasApprove && queueLen > 0, queueLen, hasApprove, sample: text.slice(0, 600) };
})()"""

_CLICK_APPROVE_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const approve = buttons.find((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  if (!approve) return { ok: false, err: 'approve-button-not-found' };
  approve.scrollIntoView({ block: 'center' });
  approve.click();
  return { ok: true, label: (approve.textContent || '').trim() };
})()"""


def _call(js_function: str, argument: object) -> str:
    return f"({js_function})({json.dumps(argument)})"


def drive_chat_turn(
    ui_url: str,
    probe: SkillChat,
    user_text: str,
    *,
    invoke_skill: bool = True,
    attachment: TextAttachment | None = None,
    spilled: bool = False,
    while_open: Callable[[ChromeMcpClient, McpPage], None] | None = None,
) -> str:
    """Act like a user: slash-pick the skill chip, attach a file, type the request, press send; returns the wire.

    ``invoke_skill=False`` sends a plain message (a follow-up turn that does not invoke the skill).
    ``spilled`` for a request over the Context Guard's cap: the server stores a file reference behind the tag.
    ``while_open`` runs after sending, with the page still open (approval cards live there).
    """
    chat_id, skill_name = probe.chat_id, probe.skill_name
    chat_url = f"{ui_url.rstrip('/')}{probe.ui_path}"
    warm_ui_route(probe.ui_path)
    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        assert bridge.get("ready") is True, json.dumps(bridge, ensure_ascii=False)
        attached = wait_for_state(
            client,
            page,
            _ATTACH_CHAT_PROBE.format(chat_id_json=json.dumps(chat_id)),
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert attached.get("ready") is True, attached
        wait_for_state(client, page, _COMPOSER_READY_JS, timeout_sec=120.0)
        prefetched = client.evaluate(page, _PREFETCH_SKILL_CATALOG_JS, timeout_sec=60.0)
        assert isinstance(prefetched, dict) and prefetched.get("ok") is True, prefetched

        if invoke_skill:
            # The palette is private to this probe's backend, so the skill's unique prefix selects exactly one entry.
            slash_query = skill_name.split("-")[0]
            typed = client.evaluate(page, _call(_TYPE_JS, "/" + slash_query), timeout_sec=15.0)
            assert isinstance(typed, dict) and typed.get("ok") is True, typed
            chip = wait_for_state(client, page, _call(_PICK_SKILL_CHIP_JS, slash_query), timeout_sec=60.0)
            pending = chip.get("pendingSkillNames")
            assert isinstance(pending, list) and any(skill_name in str(name) for name in pending), chip

        if attachment is not None:
            spec = {"name": attachment.name, "text": attachment.text}
            attached_file = client.evaluate(page, _call(_ATTACH_TEXT_FILE_JS, spec), timeout_sec=15.0)
            assert isinstance(attached_file, dict) and attached_file.get("ok") is True, attached_file
            wait_for_state(client, page, _call(_ATTACHMENT_READY_JS, attachment.name), timeout_sec=60.0)

        # Type the request and press the real send button: the composer, not a test shortcut, builds the wire.
        client.evaluate(page, _USE_AGENT_MODE_JS, timeout_sec=15.0)
        typed = client.evaluate(page, _call(_TYPE_JS, user_text), timeout_sec=15.0)
        assert isinstance(typed, dict) and typed.get("ok") is True, typed
        if "://" in user_text:
            wait_for_state(client, page, _DISMISS_LINK_PROMPT_JS, timeout_sec=15.0)
        ready = wait_for_state(client, page, _call(_SEND_READY_JS, user_text), timeout_sec=30.0)
        wire = str(ready.get("wire", ""))
        if invoke_skill:
            assert wire.startswith(f"[use {skill_name}]"), ready
        else:
            assert "[use " not in wire, ready
        sent = client.evaluate(page, _CLICK_SEND_JS, timeout_sec=15.0)
        assert isinstance(sent, dict) and sent.get("ok") is True, sent
        print(f"E2E_WIRE_MESSAGE: {wire[:400]}", flush=True)
        if len(wire) > 400:
            print(f"E2E_WIRE_MESSAGE_LENGTH: {len(wire)} chars", flush=True)
        try:
            wait_user_message_persisted(chat_id, get_e2e_api_url(), wire, exact=attachment is None, spilled=spilled)
        except pytest.fail.Exception as failure:
            page_state = client.evaluate(page, _SEND_DIAGNOSTICS_JS, timeout_sec=15.0)
            pytest.fail(f"{failure}\nbrowser state after send: {json.dumps(page_state, ensure_ascii=False)}")
        if while_open is not None:
            while_open(client, page)
        return wire


def wait_for_approval_card(client: ChromeMcpClient, page: McpPage, *, timeout_sec: float = 240.0) -> dict[str, object]:
    """Block until the tool-approval card is on screen (the run is parked at its HITL interrupt)."""
    return wait_for_state(client, page, _APPROVAL_VISIBLE_JS, timeout_sec=timeout_sec)


def click_approve(client: ChromeMcpClient, page: McpPage) -> None:
    """Press Approve on the tool-approval card, as the user would."""
    clicked = client.evaluate(page, _CLICK_APPROVE_JS, timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked
