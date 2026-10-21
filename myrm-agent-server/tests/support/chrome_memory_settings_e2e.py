"""Shared Chrome MCP helpers for /settings/memory toggles."""

from __future__ import annotations

SETTINGS_SHELL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasMemorySection =
    /Memory|记忆/.test(text) &&
    (/Conversation History Search|历史会话搜索/.test(text) || /Enable Memory|启用记忆/.test(text));
  return { ready: hasMemorySection, sample: text.slice(0, 400) };
})()"""

ENABLE_MEMORY_JS = """(() => {
  const memoryLabels = ['Enable Memory', '启用记忆'];
  const rows = Array.from(document.querySelectorAll('div.rounded-xl'));
  for (const row of rows) {
    const label = row.innerText || '';
    if (!memoryLabels.some((needle) => label.includes(needle))) continue;
    const sw = row.querySelector('button[role="switch"]');
    if (!sw) continue;
    if (sw.getAttribute('data-state') === 'unchecked') sw.click();
    return { ok: true, state: sw.getAttribute('data-state') };
  }
  return { ok: false, err: 'memory-switch-not-found' };
})()"""

_CONVERSATION_SEARCH_TOGGLE_FN = """((targetChecked) => {
  const labels = ['Conversation History Search', '历史会话搜索'];
  const rows = Array.from(document.querySelectorAll('div.rounded-xl'));
  for (const row of rows) {
    const label = row.innerText || '';
    if (!labels.some((needle) => label.includes(needle))) continue;
    const sw = row.querySelector('button[role="switch"]');
    if (!sw) continue;
    const isChecked = sw.getAttribute('data-state') === 'checked';
    if (isChecked !== targetChecked) sw.click();
    return {
      ok: sw.getAttribute('data-state') === (targetChecked ? 'checked' : 'unchecked'),
      state: sw.getAttribute('data-state'),
    };
  }
  return { ok: false, err: 'conversation-switch-not-found' };
})"""


def conversation_search_toggle_js(*, target_checked: bool) -> str:
    """Return evaluate_script payload to set conversation-search switch state."""
    return f"({_CONVERSATION_SEARCH_TOGGLE_FN})({str(target_checked).lower()})"
