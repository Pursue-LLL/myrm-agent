import type { PermissionAction, PermissionRuleConfig, SecurityConfigValue } from '@/services/config/types';

export const DOMAIN_PATTERN =
  /^(\*\.)?([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(:\d{1,5})?$/;

export const BUILTIN_BLACKLIST = ['rm -rf /', 'rm -rf /*', 'mkfs*', 'dd if=*', 'chmod 777 /*', ':(){ :|:& };:'];

export const KNOWN_PERMISSIONS = [
  'web_search_tool',
  'net_fetch',
  'shell_exec',
  'file_read',
  'file_write',
  'mcp_invoke',
  'code_interpreter_tool',
  'browser_navigate',
  'browser_fill',
  'browser_upload',
  'browser_download',
  'browser_session',
] as const;

export function flattenPermissions(
  perms: Record<string, PermissionAction | Record<string, PermissionAction>> | null | undefined,
): PermissionRuleConfig[] {
  if (!perms) return [];
  const rules: PermissionRuleConfig[] = [];
  for (const [key, value] of Object.entries(perms)) {
    if (typeof value === 'string') {
      rules.push({ permission: key, pattern: '*', action: value });
    } else {
      for (const [pattern, action] of Object.entries(value)) {
        rules.push({ permission: key, pattern, action });
      }
    }
  }
  return rules;
}

export function buildPermissions(
  rules: PermissionRuleConfig[],
): Record<string, PermissionAction | Record<string, PermissionAction>> {
  const result: Record<string, PermissionAction | Record<string, PermissionAction>> = {};
  for (const rule of rules) {
    if (!rule.permission.trim()) continue;
    if (rule.pattern === '*') {
      result[rule.permission] = rule.action;
    } else {
      const existing = result[rule.permission];
      if (typeof existing === 'object' && existing !== null) {
        existing[rule.pattern] = rule.action;
      } else {
        result[rule.permission] = { [rule.pattern]: rule.action };
      }
    }
  }
  return result;
}

export const DEFAULT_CONFIG: SecurityConfigValue = {
  permissions: {
    shell_exec: 'ask',
    mcp_invoke: 'ask',
  },
  approvalTimeoutSeconds: 120,
};

export function createEmptyRule(): PermissionRuleConfig {
  return { permission: '', pattern: '*', action: 'ask' };
}
