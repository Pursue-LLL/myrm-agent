"""The page-side scripts of the composer's slash step: attach to the chat, wait for a hydrated composer, type, pick the chip.

[INPUT]
- none (plain JavaScript source strings evaluated in the page)

[OUTPUT]
- ATTACH_CHAT_PROBE: one poll step that attaches the page to a chat and reports when the store holds it
- COMPOSER_READY_JS: the textarea exists and React owns it
- PREFETCH_SKILL_CATALOG_JS: fetch the skill catalog the slash palette lists adopted skills from
- TYPE_JS: put text in the composer the way a keystroke does (native value setter + input event)
- PICK_SKILL_CHIP_JS: one poll step of "chip present? done : click the palette entry on screen"; on a miss it reports what the page held

[POS]
Used by tests/support/chrome_skill_hooks_composer.py; split out so that file stays the Python side of driving a turn.
"""

from __future__ import annotations

ATTACH_CHAT_PROBE = """(() => {{
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
  return {{
    ready: false, chatId: store?.chatId ?? null, err: !bridge ? 'no-bridge' : null,
    loaded: Boolean(store?.isMessagesLoaded), notFound: Boolean(store?.notFound),
    loadError: Boolean(store?.loadError), loading: Boolean(store?.loading),
    attaching: Boolean(window.__MYRM_E2E_ATTACHING__),
  }};
}})()"""

# The server renders the textarea before React owns it: text typed into that markup is wiped when hydration applies
# the controlled value and never reaches the store. React marks a node it has attached to with ``__reactProps$...``.
_HYDRATED_INPUT_JS = "Object.keys(el).some((key) => key.startsWith('__reactProps$'))"

COMPOSER_READY_JS = f"""(() => {{
  const el = document.querySelector('[data-chat-input]');
  return {{ ready: Boolean(el) && {_HYDRATED_INPUT_JS}, hasInput: Boolean(el) }};
}})()"""

# Adopted local skills live in the user's skill catalog (the agent's own skill list stays empty), so the
# slash palette needs the catalog fetched, exactly like opening the skill picker does.
PREFETCH_SKILL_CATALOG_JS = """(async () => {
  await window.__MYRM_E2E_CHAT__?.prefetchSlashSkillCatalog?.();
  return { ok: true };
})()"""

TYPE_JS = f"""((text) => {{
  const el = document.querySelector('[data-chat-input]');
  if (!el) return {{ ok: false, err: 'input-not-found' }};
  const hydrated = {_HYDRATED_INPUT_JS};
  el.focus();
  // React-controlled textarea: native value setter + input event, as a real keystroke would.
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  setter.call(el, text);
  el.setSelectionRange(el.value.length, el.value.length);
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  window.__MYRM_E2E_TYPED_IN__ = performance.timeOrigin;
  return {{ ok: true, value: el.value, hydrated, timeOrigin: performance.timeOrigin }};
}})"""

# One poll step = "chip present? done : click the palette entry if it is on screen right now". The palette
# list re-renders while the skill catalog refreshes, so finding the entry and clicking it in two separate
# browser round-trips can lose the entry in between.
PICK_SKILL_CHIP_JS = """((needle) => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const pending = Array.isArray(snap.pendingSkillNames) ? snap.pendingSkillNames : [];
  if (document.querySelector('[data-testid="skill-activation-chips"]') && pending.length > 0) {
    return { ready: true, pendingSkillNames: pending };
  }
  const palette = document.querySelector('[data-testid="slash-command-palette"]');
  const items = palette ? Array.from(palette.querySelectorAll('[cmdk-item], [role="option"]')) : [];
  const target = items.find((el) => (el.textContent || '').toLowerCase().includes(needle));
  if (target) target.click();
  // Tells a page replaced after typing, a typed text the store never received, a lost caret and a crashed render
  // apart from a palette that simply did not render.
  const input = document.querySelector('[data-chat-input]');
  const state = window.__myrmChatStore?.getState?.();
  const entries = items.slice(0, 6).map((el) => (el.textContent || '').slice(0, 60));
  const overlay = document.querySelector('nextjs-portal')?.shadowRoot?.querySelector('[data-nextjs-dialog]');
  return {
    ready: false, paletteEntries: entries, hasPalette: Boolean(palette), composerText: input?.value ?? null,
    typedInThisPage: window.__MYRM_E2E_TYPED_IN__ === performance.timeOrigin, storeInput: state?.inputMessage ?? null,
    boundSkillIds: state?.agentConfig?.selectedSkillIds ?? null, caret: input?.selectionStart ?? null,
    visibility: document.visibilityState, composerFocused: document.activeElement === input,
    pageErrors: window.__MYRM_DIAG_ERRORS__ ?? null, nextErrorDialog: (overlay?.textContent ?? '').slice(0, 300) || null,
  };
})"""
