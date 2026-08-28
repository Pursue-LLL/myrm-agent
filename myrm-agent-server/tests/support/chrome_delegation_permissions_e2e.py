"""Shared Chrome MCP helpers for DPSEAG delegation permissions on Settings security."""

from __future__ import annotations

_DELEGATION_GUIDE_SCROLL_JS = """(() => {
  const nodes = Array.from(document.querySelectorAll('p,span,li,div,h3,h4'));
  const anchor = nodes.find((el) =>
    /About delegation permissions|委派权限说明/.test(el.textContent || '')
  );
  if (anchor && typeof anchor.scrollIntoView === 'function') {
    anchor.scrollIntoView({ block: 'center' });
  }
  return { scrolled: !!anchor };
})()"""


DELEGATION_PERMISSIONS_GUIDE_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle =
    /About delegation permissions|委派权限说明/.test(text);
  const hasInternal =
    /Internal sub-agent|内部子智能体|内部子代理/.test(text) &&
    /Spins up a helper agent inside Myrm|在 Myrm 内启动辅助智能体|在 Myrm 内启动辅助子代理/.test(text);
  const hasExternal =
    /External CLI agent|外部 CLI 智能体|外部 CLI 代理|外部 CLI Agent/.test(text) &&
    /Claude Code, Codex|Claude Code、Codex/.test(text);
  const hasBindingHint =
    /Settings → Agents → Subagents|设置 → 智能体 → 子智能体|「设置 → 智能体 → 子智能体」/.test(text);
  return {
    ready: hasTitle && hasInternal && hasExternal && hasBindingHint,
    hasTitle,
    hasInternal,
    hasExternal,
    hasBindingHint,
    sample: text.slice(0, 2400),
  };
})()"""


DELEGATION_PERMISSION_TYPES_IN_RULES_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasSpawnRule =
    /Internal sub-agent|内部子智能体|内部子代理/.test(text);
  const hasExternalRule =
    /External CLI agent|外部 CLI 智能体|外部 CLI 代理|外部 CLI Agent/.test(text);
  const hasPermissionSection =
    /Permission Rules|权限规则|Security Policy|安全策略/.test(text);
  return {
    ready: hasPermissionSection && hasSpawnRule && hasExternalRule,
    hasPermissionSection,
    hasSpawnRule,
    hasExternalRule,
    sample: text.slice(0, 1600),
  };
})()"""
