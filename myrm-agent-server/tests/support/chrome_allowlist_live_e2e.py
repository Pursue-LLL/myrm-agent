"""JS helpers for LIVE shell allow-always pattern Chrome E2E."""

from __future__ import annotations

_PATTERN_TOKEN = "ALLOWLIST_LIVE_PROBE"

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return {
    ready: !!bridge?.handleSubmit && !!debug.selection,
    selection: debug.selection ?? null,
    tools: bridge?.getCurrentBuiltinTools?.() ?? [],
  };
})()"""

_RUNTIME_BINDING_JS = """(() => ({
  apiBase: window.__MYRM_E2E_API_BASE__ ?? '',
  runtimeApi: window.__MYRM_E2E_RUNTIME__?.apiBase ?? '',
}))()"""

_APPROVAL_VISIBLE_JS = f"""(() => {{
  const dialog = document.querySelector('[role="dialog"]');
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  const hasAlwaysAllow = buttons.some((btn) =>
    /Always Allow|Allow Always|始终允许/.test(btn.textContent || ''),
  );
  const text = document.body?.innerText || '';
  const hasShell =
    /bash_code_execute_tool|{_PATTERN_TOKEN}|Shell|shell/i.test(text);
  return {{
    ready: Boolean(dialog) && hasApprove && hasAlwaysAllow && hasShell,
    hasDialog: Boolean(dialog),
    hasApprove,
    hasAlwaysAllow,
    hasShell,
    sample: text.slice(0, 900),
  }};
}})()"""

_CLICK_ALLOW_ALWAYS_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const allowAlways = buttons.find((btn) =>
    /Always Allow|Allow Always|始终允许/.test(btn.textContent || ''),
  );
  if (!allowAlways) {
    return { ok: false, err: 'allow-always-button-not-found' };
  }
  allowAlways.scrollIntoView({ block: 'center' });
  allowAlways.click();
  return { ok: true, label: (allowAlways.textContent || '').trim() };
})()"""

_SELECT_PATTERN_SCOPE_JS = """(() => {
  const trigger =
    document.querySelector('#allowlist-scope') ||
    document.querySelector('[id="allowlist-scope"]') ||
    Array.from(document.querySelectorAll('[role="combobox"]')).slice(-1)[0];
  if (!trigger) {
    return { ok: false, err: 'scope-trigger-not-found' };
  }
  trigger.scrollIntoView({ block: 'center' });
  trigger.click();
  const options = Array.from(document.querySelectorAll('[role="option"]'));
  const patternOption = options.find((opt) =>
    /Similar Commands|相似命令|類似コマンド|유사 명령|Ähnliche Befehle/.test(opt.textContent || ''),
  );
  if (!patternOption) {
    return { ok: false, err: 'pattern-option-not-found', optionCount: options.length };
  }
  patternOption.click();
  return { ok: true };
})()"""

_CONFIRM_ALLOW_ALWAYS_DIALOG_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const confirm = buttons.find((btn) =>
    /I understand the risks|我理解风险/.test(btn.textContent || ''),
  );
  if (!confirm) {
    return { ok: false, err: 'confirm-dialog-not-found' };
  }
  confirm.scrollIntoView({ block: 'center' });
  confirm.click();
  return { ok: true, label: (confirm.textContent || '').trim() };
})()"""

_TURN_DONE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const text = String(snap.lastAssistantSample || '');
  return {
    ready: !snap.isStreaming && text.trim().length > 0,
    isStreaming: Boolean(snap.isStreaming),
    sample: text.slice(0, 400),
  };
})()"""

SETTINGS_PATTERN_VISIBLE_JS = f"""(() => {{
  const text = document.body?.innerText || '';
  const hasPattern =
    text.includes('{_PATTERN_TOKEN} *') ||
    text.includes('{_PATTERN_TOKEN}');
  return {{ ready: hasPattern, sample: text.slice(0, 1200) }};
}})()"""
