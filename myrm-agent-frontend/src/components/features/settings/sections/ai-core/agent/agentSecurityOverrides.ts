/**
 * [INPUT] 无外部依赖（纯函数与常量）
 * [OUTPUT] KNOWN_CAPABILITIES, SecurityOverridesData, normalizeDomainInput, parseOverrides, serializeOverrides: 智能体安全覆盖配置的数据模型与解析 / 序列化
 * [POS] AgentSecurityTab 与 useSecurityListEditors 共用；空配置序列化为 null，路径白名单嵌套在 pathPolicy 下。
 */

export const KNOWN_CAPABILITIES = [
  'web_search_tool',
  'net_fetch',
  'shell_exec',
  'file_read',
  'file_write',
  'mcp_invoke',
  'code_interpreter',
] as const;

export interface SecurityOverridesData {
  capabilities: string[];
  allowedRoots: string[];
  approvalTimeoutSeconds: number | null;
  networkAllowlist: string[];
  networkBlocklist: string[];
  commandDenylist: string[];
  domainHitlEnabled: boolean;
  injectionPolicy: 'log_only' | 'fail_closed' | null;
}

const EMPTY_DATA: SecurityOverridesData = {
  capabilities: [],
  allowedRoots: [],
  approvalTimeoutSeconds: null,
  networkAllowlist: [],
  networkBlocklist: [],
  commandDenylist: [],
  domainHitlEnabled: false,
  injectionPolicy: null,
};

export function normalizeDomainInput(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/\/.*$/, '');
}

export function parseOverrides(raw: Record<string, unknown> | null): SecurityOverridesData {
  if (!raw) {
    return EMPTY_DATA;
  }

  const caps = Array.isArray(raw.capabilities) ? (raw.capabilities as string[]) : [];

  const pp = raw.pathPolicy as Record<string, unknown> | undefined;
  const roots = Array.isArray(pp?.allowedRoots) ? (pp.allowedRoots as string[]) : [];

  const timeout = typeof raw.approvalTimeoutSeconds === 'number' ? raw.approvalTimeoutSeconds : null;

  const allowlist = Array.isArray(raw.networkAllowlist) ? (raw.networkAllowlist as string[]) : [];
  const blocklist = Array.isArray(raw.networkBlocklist) ? (raw.networkBlocklist as string[]) : [];
  const cmdDenylist = Array.isArray(raw.commandDenylist) ? (raw.commandDenylist as string[]) : [];

  const domainHitl = raw.domainHitlEnabled === true;
  const injPolicy =
    raw.injectionPolicy === 'fail_closed'
      ? ('fail_closed' as const)
      : raw.injectionPolicy === 'log_only'
        ? ('log_only' as const)
        : null;

  return {
    capabilities: caps,
    allowedRoots: roots,
    approvalTimeoutSeconds: timeout,
    networkAllowlist: allowlist,
    networkBlocklist: blocklist,
    commandDenylist: cmdDenylist,
    domainHitlEnabled: domainHitl,
    injectionPolicy: injPolicy,
  };
}

export function serializeOverrides(data: SecurityOverridesData): Record<string, unknown> | null {
  const hasContent =
    data.capabilities.length > 0 ||
    data.allowedRoots.length > 0 ||
    data.approvalTimeoutSeconds !== null ||
    data.networkAllowlist.length > 0 ||
    data.networkBlocklist.length > 0 ||
    data.commandDenylist.length > 0 ||
    data.domainHitlEnabled ||
    data.injectionPolicy !== null;

  if (!hasContent) {
    return null;
  }

  const result: Record<string, unknown> = {};
  if (data.capabilities.length > 0) {
    result.capabilities = data.capabilities;
  }
  if (data.allowedRoots.length > 0) {
    result.pathPolicy = { allowedRoots: data.allowedRoots };
  }
  if (data.approvalTimeoutSeconds !== null) {
    result.approvalTimeoutSeconds = data.approvalTimeoutSeconds;
  }
  if (data.networkAllowlist.length > 0) {
    result.networkAllowlist = data.networkAllowlist;
  }
  if (data.networkBlocklist.length > 0) {
    result.networkBlocklist = data.networkBlocklist;
  }
  if (data.commandDenylist.length > 0) {
    result.commandDenylist = data.commandDenylist;
  }
  if (data.domainHitlEnabled) {
    result.domainHitlEnabled = true;
  }
  if (data.injectionPolicy !== null) {
    result.injectionPolicy = data.injectionPolicy;
  }
  return result;
}
