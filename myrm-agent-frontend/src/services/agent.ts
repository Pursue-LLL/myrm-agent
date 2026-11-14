import { apiRequest } from '@/lib/api';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import type { AgentSkillConfigMap } from '@/types/agentSkillConfig';
import { throwUserAgentFetchError } from './agentFetchError';

/** Largest `page_size` the roster endpoint accepts. */
const AGENT_LIST_MAX_PAGE_SIZE = 100;

/** Metadata for a built-in subagent preset exposed by the Agent editor. */
export interface SubagentPresetItem {
  id: string;
  display_name: string;
  description: string;
  required_builtin_tools: string[];
}

/** Load the built-in specialists that can be bound through `subagent_ids`. */
export async function getSubagentPresets(): Promise<SubagentPresetItem[]> {
  return apiRequest<SubagentPresetItem[]>('/agents/subagent-presets', { method: 'GET', silent: true });
}

export interface AgentModelSelection {
  providerId: string;
  model: string;
  fallbackProviderId?: string;
  fallbackModel?: string;
  safetyFallbackProviderId?: string;
  safetyFallbackModel?: string;
  modelKwargs?: Record<string, unknown>;
  routingEnabled?: boolean;
  lightProviderId?: string;
  lightModel?: string;
  reasoningProviderId?: string;
  reasoningModel?: string;
}

export interface CommandBindingConfig {
  command_name: string;
  skill_ids: string[];
  description?: string;
  aliases?: string[];
  instruction?: string;
}

export type OpenAPIAuthType = 'none' | 'api_key' | 'bearer' | 'basic' | 'oauth2_client_credentials';

export interface OpenAPIAuthConfig {
  type: OpenAPIAuthType;
  api_key?: string;
  api_key_header?: string;
  api_key_location?: 'header' | 'query';
  bearer_token?: string;
  username?: string;
  password?: string;
  token_url?: string;
  client_id?: string;
  client_secret?: string;
  scopes?: string[];
}

export interface OpenAPIServiceConfig {
  name: string;
  spec_url?: string;
  spec_content?: string;
  base_url?: string;
  description?: string;
  auth?: OpenAPIAuthConfig;
  selected_endpoints?: string[];
  enabled: boolean;
  request_timeout?: number;
  max_retries?: number;
}

export type AgentType = 'individual' | 'team';
export type WorkspacePolicy = 'INHERIT_REQUESTER' | 'READ_ONLY_SANDBOX';
export type SessionResetMode = 'persistent' | 'daily' | 'idle';

export interface AgentSessionPolicy {
  mode: SessionResetMode;
  daily_reset_hour: number;
  idle_minutes: number;
}

export interface NotifyTarget {
  channel: string;
  recipient_id: string;
  label?: string;
}

export interface ToolGatewayConfigDTO {
  use_gateway: boolean;
  gateway_url?: string | null;
  auth_token?: string | null;
}

export interface TrustedDesktopAppEntry {
  name: string;
  app_id?: string;
}

export interface Agent {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  avatar_url?: string;
  home_directory?: string;
  is_built_in?: boolean;
  agent_type?: AgentType;
  system_prompt?: string;
  mcp_ids?: string[];
  mcp_tool_selections?: Record<string, string[]>;
  skill_ids?: string[];
  mounted_skill_ids?: string[];
  skill_configs?: AgentSkillConfigMap | null;
  enabled_builtin_tools?: string[] | null;
  browser_source?: string | null;
  dialog_policy?: string | null;
  session_recording?: string | null;
  auto_restore_domains?: string[] | null;
  suggestion_prompts?: string[] | null;
  model_selection?: AgentModelSelection | null;
  security_overrides?: Record<string, unknown> | null;
  default_security_preset?: 'hitl' | 'accept_edits' | 'explore' | null;
  subagent_ids?: string[];
  max_iterations?: number | null;
  workspace_policy?: WorkspacePolicy;
  engine_params?: Record<string, unknown> | null;
  openapi_services?: OpenAPIServiceConfig[];
  memory_decay_profile?: 'permanent' | 'normal' | 'fast';
  memory_extraction_preset?: 'none' | 'auto' | 'persona' | 'work_assistant' | 'research';
  session_policy?: AgentSessionPolicy | null;
  command_bindings?: CommandBindingConfig[] | null;
  notify_targets?: NotifyTarget[] | null;
  tool_gateway_config?: ToolGatewayConfigDTO | null;
  allow_discovery?: boolean;
  cron_post_run_verify?: boolean;
  trusted_desktop_apps?: TrustedDesktopAppEntry[];
  busy_input_mode?: 'redirect' | 'steer' | 'queue' | null;
  snapshot_count?: number;
  snapshot_saved?: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentListItem {
  id: string;
  name: string;
  description?: string;
  avatar_url?: string;
  is_built_in?: boolean;
  agent_type?: AgentType;
  prompt_mode?: 'full' | 'search';
  skill_ids?: string[];
  mcp_ids?: string[];
  subagent_ids?: string[];
  enabled_builtin_tools?: string[] | null;
  model_selection?: AgentModelSelection | null;
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  name: string;
  description?: string;
  avatar_url?: string;
  home_directory?: string;
  is_built_in?: boolean;
  agent_type?: AgentType;
  system_prompt?: string;
  mcp_ids?: string[];
  mcp_tool_selections?: Record<string, string[]>;
  skill_ids?: string[];
  mounted_skill_ids?: string[];
  skill_configs?: AgentSkillConfigMap | null;
  enabled_builtin_tools?: string[];
  browser_source?: string | null;
  dialog_policy?: string | null;
  session_recording?: string | null;
  auto_restore_domains?: string[];
  suggestion_prompts?: string[] | null;
  model_selection?: AgentModelSelection | null;
  security_overrides?: Record<string, unknown> | null;
  default_security_preset?: 'hitl' | 'accept_edits' | 'explore' | null;
  subagent_ids?: string[];
  max_iterations?: number | null;
  workspace_policy?: WorkspacePolicy;
  engine_params?: Record<string, unknown> | null;
  openapi_services?: OpenAPIServiceConfig[];
  memory_decay_profile?: 'permanent' | 'normal' | 'fast';
  memory_extraction_preset?: 'none' | 'auto' | 'persona' | 'work_assistant' | 'research';
  session_policy?: AgentSessionPolicy | null;
  command_bindings?: CommandBindingConfig[] | null;
  notify_targets?: NotifyTarget[] | null;
  tool_gateway_config?: ToolGatewayConfigDTO | null;
  allow_discovery?: boolean;
  cron_post_run_verify?: boolean;
  trusted_desktop_apps?: TrustedDesktopAppEntry[];
  busy_input_mode?: 'redirect' | 'steer' | 'queue' | null;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  avatar_url?: string;
  home_directory?: string;
  is_built_in?: boolean;
  agent_type?: AgentType;
  system_prompt?: string;
  mcp_ids?: string[];
  mcp_tool_selections?: Record<string, string[]>;
  skill_ids?: string[];
  mounted_skill_ids?: string[];
  skill_configs?: AgentSkillConfigMap | null;
  enabled_builtin_tools?: string[];
  browser_source?: string | null;
  dialog_policy?: string | null;
  session_recording?: string | null;
  auto_restore_domains?: string[];
  suggestion_prompts?: string[] | null;
  model_selection?: AgentModelSelection | null;
  security_overrides?: Record<string, unknown> | null;
  default_security_preset?: 'hitl' | 'accept_edits' | 'explore' | null;
  subagent_ids?: string[];
  max_iterations?: number | null;
  workspace_policy?: WorkspacePolicy;
  engine_params?: Record<string, unknown> | null;
  openapi_services?: OpenAPIServiceConfig[];
  memory_decay_profile?: 'permanent' | 'normal' | 'fast';
  memory_extraction_preset?: 'none' | 'auto' | 'persona' | 'work_assistant' | 'research';
  session_policy?: AgentSessionPolicy | null;
  command_bindings?: CommandBindingConfig[] | null;
  notify_targets?: NotifyTarget[] | null;
  tool_gateway_config?: ToolGatewayConfigDTO | null;
  allow_discovery?: boolean;
  cron_post_run_verify?: boolean;
  trusted_desktop_apps?: TrustedDesktopAppEntry[];
  busy_input_mode?: 'redirect' | 'steer' | 'queue' | null;
}

export interface AgentListResponse {
  items: AgentListItem[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}

export async function listAgents(page: number, pageSize: number): Promise<AgentListResponse> {
  return apiRequest<AgentListResponse>(`/user-agents?page=${page}&page_size=${pageSize}`, {
    method: 'GET',
    silent: true,
  });
}

/**
 * Every agent of the roster, newest first. It follows the pagination so a long roster is never cut off, and lists an
 * agent once even when a concurrent create shifts it onto the next page. A failing page rejects the whole load.
 */
export async function listAllAgents(): Promise<AgentListItem[]> {
  const agentsById = new Map<string, AgentListItem>();
  for (let page = 1; ; page += 1) {
    const { items, pagination } = await listAgents(page, AGENT_LIST_MAX_PAGE_SIZE);
    const knownBefore = agentsById.size;
    for (const item of items) {
      agentsById.set(item.id, item);
    }
    // A page that adds nothing new ends the loop even if the server still announces more pages.
    if (!pagination.has_next || agentsById.size === knownBefore) {
      return [...agentsById.values()];
    }
  }
}

/** 不带 `show_system_prompt=true` 读取（或读者不是所有者）时，服务端用它代替 `system_prompt`。 */
export const HIDDEN_SYSTEM_PROMPT = '⚠️ [Hidden for security]';

/**
 * 获取单个智能体详情
 */
export async function getAgent(
  agentId: string,
  showSystemPrompt: boolean = false,
  signal?: AbortSignal,
): Promise<Agent> {
  const url = showSystemPrompt
    ? `${getBackendUrl()}/api/v1/user-agents/${agentId}?show_system_prompt=true`
    : `${getBackendUrl()}/api/v1/user-agents/${agentId}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    cache: 'no-store',
    signal,
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'get agent');
  }

  const result = await response.json();
  return result.data;
}

/**
 * 创建智能体
 */
export async function createAgent(data: AgentCreate): Promise<Agent> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'create agent');
  }

  const result = await response.json();
  return result.data;
}

/**
 * 更新智能体
 */
export async function updateAgent(agentId: string, data: AgentUpdate): Promise<Agent> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'update agent');
  }

  const result = await response.json();
  return result.data;
}

/**
 * 删除智能体
 */
export async function deleteAgent(agentId: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (response.status === 404) {
    return;
  }
  if (!response.ok) {
    await throwUserAgentFetchError(response, 'delete agent');
  }
}

export async function cloneAgent(agentId: string, name?: string): Promise<Agent> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/clone`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(name ? { name } : {}),
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'clone agent');
  }

  const result = await response.json();
  return result.data;
}
