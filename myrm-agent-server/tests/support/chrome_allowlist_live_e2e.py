"""JS helpers for LIVE shell allow-always pattern Chrome E2E."""

from __future__ import annotations

_PATTERN_TOKEN = "ALLOWLIST_LIVE_PROBE"

_RECOVER_HITL_JS = """((chatId) => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.recoverHitlStream) {
    return { ok: false, err: 'missing-recoverHitlStream' };
  }
  const timeoutMs = 15000;
  const queueSnapshot = () =>
    Number(window.__MYRM_E2E_CHAT__?.toolApprovalSnapshot?.()?.queueLen ?? 0);
  return Promise.race([
    bridge.recoverHitlStream(String(chatId || '')),
    new Promise((resolve) =>
      setTimeout(
        () =>
          resolve({
            ok: true,
            timedOut: true,
            queueLen: queueSnapshot(),
          }),
        timeoutMs,
      ),
    ),
  ]).then(
    (result) => result,
    (error) => ({ ok: false, err: String(error) }),
  );
})"""

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
  const approvalSnap = window.__MYRM_E2E_CHAT__?.toolApprovalSnapshot?.() ?? {{}};
  const queueLen = Number(approvalSnap.queueLen ?? 0);
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  const hasAlwaysAllow = buttons.some((btn) =>
    /Always Allow|Allow Always|始终允许/.test(btn.textContent || ''),
  );
  const text = document.body?.innerText || '';
  const hasShell =
    /bash_code_execute_tool|{_PATTERN_TOKEN}|Shell|shell/i.test(text);
  const drawer =
    document.querySelector('[data-vaul-drawer]') ||
    document.querySelector('[role="dialog"]') ||
    document.querySelector('[data-testid="approval-drawer"]');
  const ready = hasApprove && hasAlwaysAllow && (hasShell || queueLen > 0);
  return {{
    ready,
    queueLen,
    queueTools: approvalSnap.tools ?? [],
    hasDialog: Boolean(drawer),
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

_SELECT_PATTERN_SCOPE_JS = """(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let attempt = 0; attempt < 24; attempt += 1) {
    const trigger =
      document.querySelector('#allowlist-scope') ||
      document.querySelector('[id="allowlist-scope"]');
    if (!trigger) {
      await sleep(200);
      continue;
    }
    trigger.scrollIntoView({ block: 'center' });
    trigger.click();
    await sleep(120);
    let patternOption =
      document.querySelector('[role="option"][data-value="pattern"]') ||
      document.querySelector('[data-value="pattern"]');
    if (!patternOption) {
      const options = Array.from(document.querySelectorAll('[role="option"]'));
      patternOption =
        options.find((opt) =>
          /Similar Commands|相似命令|類似コマンド|유사 명령|Ähnliche Befehle/.test(opt.textContent || ''),
        ) || null;
    }
    if (patternOption) {
      patternOption.click();
      return { ok: true, attempt };
    }
    await sleep(150);
  }
  return {
    ok: false,
    err: 'pattern-option-not-found',
    optionCount: document.querySelectorAll('[role="option"]').length,
    hasTrigger: Boolean(document.querySelector('#allowlist-scope')),
  };
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

SETTINGS_PATTERN_VISIBLE_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasPattern =
    text.includes('curl -sS *') ||
    text.includes('ALLOWLIST_LIVE_PROBE');
  return { ready: hasPattern, sample: text.slice(0, 1200) };
})()"""
