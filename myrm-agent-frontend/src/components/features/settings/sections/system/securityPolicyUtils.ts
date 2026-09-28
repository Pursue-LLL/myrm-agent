import type { PermissionAction, PermissionRuleConfig, SecurityConfigValue } from '@/services/config/types';

export const DOMAIN_PATTERN =
  /^(\*\.)?([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(:\d{1,5})?$/;

export const BUILTIN_BLACKLIST = ['rm -rf /', 'rm -rf /*', 'mkfs*', 'dd if=*', 'chmod 777 /*', ':(){ :|:& };:'];

export const KNOWN_PERMISSIONS = [
  'knowledge_read',
  'knowledge_write',
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
  'spawn_subagent',
  'invoke_external_agent',
] as const;

export type CapabilitySurfaceKey =
  'knowledge_read' | 'knowledge_write' | 'web_egress' | 'candidate_create' | 'remote_tools' | 'local_filesystem';

export interface CapabilitySurfaceMeta {
  key: CapabilitySurfaceKey;
  label: string;
  description: string;
  tools: readonly string[];
  defaultAction: PermissionAction;
}

export const CAPABILITY_SURFACES: readonly CapabilitySurfaceMeta[] = [
  {
    key: 'knowledge_read',
    label: 'Knowledge Read (Wiki / RAG)',
    description: 'Querying and retrieving personal wiki, documents, and reference knowledge bases.',
    tools: ['wiki_query_tool'],
    defaultAction: 'allow',
  },
  {
    key: 'knowledge_write',
    label: 'Knowledge Ingest & Mutation',
    description: 'Ingesting or modifying wiki pages, memory summaries, and persistent corporate knowledge.',
    tools: ['wiki_apply_tool', 'wiki_ingest_tool'],
    defaultAction: 'ask',
  },
  {
    key: 'web_egress',
    label: 'Web Egress & Retrieval',
    description: 'Outbound network requests, search engines, and live website browsing.',
    tools: ['web_search', 'net_fetch', 'browser_navigate', 'fetch_web_content', 'web_search_tool'],
    defaultAction: 'allow',
  },
  {
    key: 'candidate_create',
    label: 'Staged Candidate Artifacts',
    description: 'Generating non-destructive preview drafts and staging proposals before execution.',
    tools: ['candidate_create'],
    defaultAction: 'allow',
  },
  {
    key: 'remote_tools',
    label: 'Remote Tools & Delegation',
    description: 'External MCP tool invocations, CLI external subagents, and SSH remote commands.',
    tools: ['mcp_invoke', 'invoke_external_agent', 'remote_command_exec', 'remote_tunnel_open'],
    defaultAction: 'ask',
  },
  {
    key: 'local_filesystem',
    label: 'Local File Operations',
    description: 'Reading, writing, modifying, and listing local files in the workspace.',
    tools: ['file_read', 'file_write', 'file_edit', 'file_delete', 'list_directory', 'search_files', 'get_file_info'],
    defaultAction: 'ask',
  },
] as const;

export type CapabilityMatrix = Record<CapabilitySurfaceKey, PermissionAction>;

export interface CapabilityPreset {
  id: string;
  name: string;
  description: string;
  matrix: CapabilityMatrix;
}

export const CAPABILITY_PRESETS: readonly CapabilityPreset[] = [
  {
    id: 'guarded',
    name: 'Guarded (High Security)',
    description: 'Strict fail-safe boundary: write, remote tools, and file mutations are strictly blocked.',
    matrix: {
      knowledge_read: 'allow',
      knowledge_write: 'deny',
      web_egress: 'ask',
      candidate_create: 'deny',
      remote_tools: 'deny',
      local_filesystem: 'deny',
    },
  },
  {
    id: 'balanced',
    name: 'Balanced (Recommended)',
    description:
      'Safe default for daily productivity: mutations require explicit confirmation, safe reads are allowed.',
    matrix: {
      knowledge_read: 'allow',
      knowledge_write: 'ask',
      web_egress: 'allow',
      candidate_create: 'allow',
      remote_tools: 'ask',
      local_filesystem: 'ask',
    },
  },
  {
    id: 'geek',
    name: 'Autonomous (Developer)',
    description: 'Minimal friction for autonomous coding and local research. Only external remote tools ask.',
    matrix: {
      knowledge_read: 'allow',
      knowledge_write: 'allow',
      web_egress: 'allow',
      candidate_create: 'allow',
      remote_tools: 'ask',
      local_filesystem: 'allow',
    },
  },
] as const;

export function deriveCapabilityMatrix(
  matrixFromConfig?: Record<string, PermissionAction>,
  rules?: PermissionRuleConfig[],
): CapabilityMatrix {
  const result: Partial<CapabilityMatrix> = {};
  for (const surface of CAPABILITY_SURFACES) {
    if (matrixFromConfig && matrixFromConfig[surface.key]) {
      result[surface.key] = matrixFromConfig[surface.key];
      continue;
    }
    if (rules && rules.length > 0) {
      const directRule = rules.find((r) => r.permission === surface.key);
      if (directRule) {
        result[surface.key] = directRule.action;
        continue;
      }
    }
    result[surface.key] = surface.defaultAction;
  }
  return result as CapabilityMatrix;
}

export function syncCapabilityActionToRules(
  currentRules: PermissionRuleConfig[],
  surfaceKey: CapabilitySurfaceKey,
  action: PermissionAction,
): PermissionRuleConfig[] {
  const meta = CAPABILITY_SURFACES.find((s) => s.key === surfaceKey);
  const targetPermissions = new Set<string>([surfaceKey, ...(meta ? meta.tools : [])]);
  const preserved = currentRules.filter((r) => !targetPermissions.has(r.permission));
  return [...preserved, { permission: surfaceKey, pattern: '*', action }];
}

export function flattenPermissions(
  perms: Record<string, PermissionAction | Record<string, PermissionAction>> | null | undefined,
): PermissionRuleConfig[] {
  if (!perms) {
    return [];
  }
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
    if (!rule.permission.trim()) {
      continue;
    }
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
