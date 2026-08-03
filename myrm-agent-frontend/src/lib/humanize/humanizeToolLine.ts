import type { TranslateFn } from './types';
import type { HumanizeContext } from './extractContext';
import { parseMcpToolName } from './extractContext';
import { platformLabelFromTarget } from './scopeNote';
import { displayUrlHost } from './pathUtils';

function normalizeToolKey(toolName: string): string {
  return toolName.replace(/_tool$/, '').replace(/-/g, '_');
}

function isMissingTranslation(key: string, hit: string): boolean {
  return !hit || hit === key || hit.endsWith(`.${key}`) || hit.endsWith(key);
}

function translate(t: TranslateFn, key: string, values?: Record<string, string>): string {
  const hit = t(key, values);
  if (!isMissingTranslation(key, hit)) {
    return hit;
  }
  const toolLabel = values?.tool ?? values?.filename ?? values?.name ?? key;
  const used = t('fallback.used_tool', { tool: String(toolLabel) });
  if (!isMissingTranslation('fallback.used_tool', used)) {
    return used;
  }
  return String(toolLabel);
}

/** Human-readable one-liner for tools in progress / approval / ask modes. */
export function humanizeToolLine(
  toolName: string,
  ctx: HumanizeContext,
  t: TranslateFn,
  mode: 'progress' | 'approval' | 'ask' = 'progress',
): string {
  const normalized = normalizeToolKey(toolName);
  const prefix = mode;
  const fallbackFile = t('fallback.file');
  const filename = ctx.filename ?? (isMissingTranslation('fallback.file', fallbackFile) ? 'file' : fallbackFile);

  if (normalized.includes('file_read') || normalized === 'read_file') {
    return translate(t, `${prefix}.file_read`, { filename });
  }
  if (
    normalized.includes('file_write') ||
    normalized.includes('file_edit') ||
    normalized.includes('file_editor') ||
    normalized.includes('text_editor') ||
    normalized === 'write_file' ||
    normalized === 'replace_in_file'
  ) {
    const askKey = mode === 'ask' ? 'file_write_ask' : 'file_write';
    return translate(t, `${prefix}.${askKey}`, { filename });
  }
  if (toolName.startsWith('browser_') || normalized.startsWith('browser_')) {
    if (ctx.url) {
      return translate(t, `${prefix}.browser_url`, { url: displayUrlHost(ctx.url) });
    }
    return translate(t, `${prefix}.browser_generic`, {});
  }
  if (normalized.includes('bash') || normalized === 'execute_code' || normalized === 'run_shell') {
    if (ctx.description) {
      return translate(t, `${prefix}.shell_with_desc`, { description: ctx.description });
    }
    if (ctx.command) {
      return translate(t, `${prefix}.shell`, { command: ctx.command });
    }
    return translate(t, `${prefix}.shell_generic`, {});
  }
  if (normalized.includes('web_search') || normalized === 'grep') {
    if (ctx.query) {
      return translate(t, `${prefix}.web_search`, { query: ctx.query });
    }
    return translate(t, `${prefix}.web_search_generic`, {});
  }
  if (normalized.includes('web_fetch')) {
    if (ctx.url) {
      return translate(t, `${prefix}.web_fetch`, { url: displayUrlHost(ctx.url) });
    }
    return translate(t, `${prefix}.web_fetch_generic`, {});
  }
  if (normalized.includes('memory')) {
    return translate(t, `${prefix}.memory_generic`, {});
  }
  if (normalized.includes('kanban') || normalized === 'todo_write') {
    if (ctx.text) {
      return translate(t, `${prefix}.kanban`, { task: ctx.text });
    }
    return translate(t, `${prefix}.kanban_generic`, {});
  }
  if (normalized === 'save_skill' || toolName === 'save_skill_tool') {
    if (ctx.skillName) {
      return translate(t, `${prefix}.save_skill`, { name: ctx.skillName });
    }
    return translate(t, `${prefix}.save_skill_generic`, {});
  }
  if (normalized === 'skill_manage' || toolName === 'skill_manage_tool') {
    const action = typeof ctx.action === 'string' ? ctx.action.trim() : '';
    if (action && action !== 'save') {
      return translate(t, `${prefix}.skill_generic`, {});
    }
    if (ctx.skillName) {
      return translate(t, `${prefix}.save_skill`, { name: ctx.skillName });
    }
    return translate(t, `${prefix}.save_skill_generic`, {});
  }
  if (
    normalized.includes('send_message') ||
    normalized.includes('send_file') ||
    toolName === 'channel_send' ||
    toolName === 'send_message_tool' ||
    toolName === 'send_file_tool'
  ) {
    if (ctx.target) {
      const destination = platformLabelFromTarget(ctx.target);
      return translate(t, `${prefix}.send_message`, { destination });
    }
    return translate(t, `${prefix}.send_message_generic`, {});
  }
  if (normalized.includes('skill')) {
    if (ctx.skillName) {
      return translate(t, `${prefix}.skill`, { name: ctx.skillName });
    }
    return translate(t, `${prefix}.skill_generic`, {});
  }
  if (toolName.startsWith('mcp__')) {
    const { server, tool } = parseMcpToolName(toolName);
    if (server && tool) {
      const label = tool.replace(/_/g, ' ');
      return translate(t, `${prefix}.mcp`, { server, tool: label });
    }
  }

  const label = toolName
    .replace(/_tool$/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return translate(t, 'fallback.used_tool', { tool: label });
}
