"""Page-side scripts the clarify Skip live E2E evaluates through the E2E chat bridge.

[INPUT]
- window.__MYRM_E2E_CHAT__ (POS: dev-only bridge that `E2EChatBridge.tsx` installs in the WebUI)

[OUTPUT]
- *_JS: expressions for `McpChatSession.evaluate` — enable structured clarify, pin the lite model, dismiss the migration
  prompt, release the UI stream, read clarify-form readiness, click Skip (DOM or bridge), read the UI skip-done state

[POS]
Single source for the page-side scripts of the clarify Skip E2E, kept apart from the Python control flow.
"""

from __future__ import annotations

ENABLE_STRUCTURED_CLARIFY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setCurrentBuiltinTools) {
    return { ok: false, err: 'no-bridge' };
  }
  bridge.setCurrentBuiltinTools(['structured_clarify']);
  const tools = bridge.getCurrentBuiltinTools?.() ?? [];
  return { ok: tools.includes('structured_clarify'), tools };
})()"""

PIN_LITE_MODEL_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) {
    return { ok: false, err: 'no-bridge' };
  }
  try {
    const pinned = await bridge.pinLiteModelForE2e();
    const debug = bridge.debugProviderState?.() ?? {};
    return {
      ok: true,
      pinned,
      selection: debug.selection ?? null,
      agentModelSelection: debug.agentModelSelection ?? null,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

DISMISS_MIGRATION_JS = """(() => {
  try {
    localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  const buttons = [...document.querySelectorAll('button')];
  const later = buttons.find((b) => /稍后再说|Later|Skip for now|Not now/i.test((b.textContent || '').trim()));
  if (later) {
    later.click();
    return { ok: true, clicked: 'later' };
  }
  return { ok: true, clicked: null };
})()"""

RELEASE_UI_STREAM_FOR_API_JS = """(() => {
  const fn = window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume;
  return typeof fn === 'function' ? fn() : { ok: false, err: 'missing-bridge-method' };
})()"""

CLARIFY_FORM_READY_JS = """(() => {
  const main = document.querySelector('main');
  const text = main?.innerText || '';
  const buttons = [...(main?.querySelectorAll('button') ?? [])];
  const skipBtn = buttons.find((b) => /^(Skip|跳过)$/i.test((b.textContent || '').trim()));
  const hasForm = /Needs your input|Clarification form|澄清表单|需要你确认/i.test(text)
    || Boolean(document.querySelector('[data-clarification-form]'));
  return {
    ready: Boolean(skipBtn),
    hasSkip: Boolean(skipBtn),
    hasForm,
    sample: text.slice(0, 800),
  };
})()"""

CLICK_SKIP_JS = """(() => {
  const main = document.querySelector('main');
  const buttons = [...(main?.querySelectorAll('button') ?? [])];
  const skipBtn = buttons.find((b) => /^(Skip|跳过)$/i.test((b.textContent || '').trim()));
  if (!skipBtn) {
    return { ok: false, err: 'no-skip-btn' };
  }
  skipBtn.click();
  return { ok: true };
})()"""

SKIP_VIA_BRIDGE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.skipActiveClarificationForE2e) {
    return { ok: false, err: 'no-bridge' };
  }
  try {
    const started = bridge.skipActiveClarificationForE2e();
    return { ok: true, started };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

UI_SKIP_DONE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const sample = String(snap.lastAssistantSample || '');
  const doneSkipped = /DONE-SKIPPED/i.test(sample);
  // The card closing on click is no evidence: a skip that reached no agent closes it too. Text after the card is.
  return {
    ready: doneSkipped || (snap.clarificationAnswered === true && sample.trim() !== ''),
    clarificationAnswered: snap.clarificationAnswered === true,
    doneSkipped,
    isStreaming: Boolean(snap.isStreaming),
    sample: sample.slice(0, 240),
  };
})()"""
