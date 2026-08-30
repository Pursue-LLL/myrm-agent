"""Shared Chrome MCP helpers for Settings allowlist (pattern scope)."""

from __future__ import annotations

from tests.support.allowlist_test_seed import PATTERN_ENTRY_COMMAND_PATTERN, PATTERN_ENTRY_TOOL

SETTINGS_SECURITY_SHELL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasAllowlist =
    /Allowlist Records|允许记录/.test(text) &&
    (/Allow Always|始终允许/.test(text) || /Security Policy|安全策略/.test(text));
  return { ready: hasAllowlist, sample: text.slice(0, 500) };
})()"""


REFRESH_ALLOWLIST_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const refresh = buttons.find((btn) => /Refresh|刷新|重新整理|更新/.test(btn.textContent || ''));
  if (!refresh) return { ok: false, err: 'no-refresh-button' };
  refresh.click();
  return { ok: true };
})()"""


def allowlist_pattern_visible_js() -> str:
    pattern = PATTERN_ENTRY_COMMAND_PATTERN.replace("\\", "\\\\").replace("'", "\\'")
    tool = PATTERN_ENTRY_TOOL.replace("\\", "\\\\").replace("'", "\\'")
    return f"""(() => {{
  const nodes = Array.from(document.querySelectorAll('h1,h2,h3,h4,p,span,div'));
  const anchor = nodes.find((el) => /Allowlist Records|允许记录/.test(el.textContent || ''));
  if (anchor && typeof anchor.scrollIntoView === 'function') {{
    anchor.scrollIntoView({{ block: 'center' }});
  }}
  const text = document.body?.innerText || '';
  const hasPattern = text.includes('{pattern}');
  const hasTool = text.includes('{tool}');
  const hasGranularity =
    /Similar Commands|相似命令|類似コマンド|유사 명령|Ähnliche Befehle|pattern/i.test(text);
  return {{
    ready: hasPattern && hasTool,
    hasPattern,
    hasTool,
    hasGranularity,
    sample: text.slice(0, 1200),
  }};
}})()"""
