import { apiRequest } from '@/lib/api';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

export const DEFAULT_PERSONALITY_STYLE = 'professional' as const;

/** 24 built-in presets exceed API default page_size=20. */
export const AGENT_LIST_BUILTIN_PAGE_SIZE = 50;

export interface AgentModelSelection {
  providerId: string;
  model: string;
  fallbackProviderId?: string;
  fallbackModel?: string;
  safetyFallbackProviderId?: string;
  safetyFallbackModel?: string;
  modelKwargs?: Record<string, unknown>;
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
export type WorkspacePolicy = 'INHERIT_REQUESTER' | 'ISOLATED_COPY' | 'READ_ONLY_SANDBOX';
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
  skill_configs?: Record<string, { is_core?: boolean }> | null;
  enabled_builtin_tools?: string[] | null;
  browser_source?: string | null;
  dialog_policy?: string | null;
  session_recording?: string | null;
  auto_restore_domains?: string[] | null;
  suggestion_prompts?: string[] | null;
  model_selection?: AgentModelSelection | null;
  security_overrides?: Record<string, unknown> | null;
  prompt_mode?: 'full' | 'lean' | 'naked';
  personality_style?: string;
  subagent_ids?: string[];
  max_iterations?: number | null;
  workspace_policy?: WorkspacePolicy;
  engine_params?: Record<string, unknown> | null;
  openapi_services?: OpenAPIServiceConfig[];
  memory_decay_profile?: 'permanent' | 'normal' | 'fast';
  session_policy?: AgentSessionPolicy | null;
  command_bindings?: CommandBindingConfig[] | null;
  notify_targets?: NotifyTarget[] | null;
  tool_gateway_config?: ToolGatewayConfigDTO | null;
  allow_discovery?: boolean;
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
  skill_ids?: string[];
  mcp_ids?: string[];
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
  skill_configs?: Record<string, { is_core?: boolean }> | null;
  enabled_builtin_tools?: string[];
  browser_source?: string | null;
  dialog_policy?: string | null;
  session_recording?: string | null;
  auto_restore_domains?: string[];
  suggestion_prompts?: string[] | null;
  model_selection?: AgentModelSelection | null;
  security_overrides?: Record<string, unknown> | null;
  prompt_mode?: 'full' | 'lean' | 'naked';
  personality_style?: string;
  subagent_ids?: string[];
  max_iterations?: number | null;
  workspace_policy?: WorkspacePolicy;
  engine_params?: Record<string, unknown> | null;
  openapi_services?: OpenAPIServiceConfig[];
  memory_decay_profile?: 'permanent' | 'normal' | 'fast';
  session_policy?: AgentSessionPolicy | null;
  command_bindings?: CommandBindingConfig[] | null;
  notify_targets?: NotifyTarget[] | null;
  tool_gateway_config?: ToolGatewayConfigDTO | null;
  allow_discovery?: boolean;
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
  skill_configs?: Record<string, { is_core?: boolean }> | null;
  enabled_builtin_tools?: string[];
  browser_source?: string | null;
  dialog_policy?: string | null;
  session_recording?: string | null;
  auto_restore_domains?: string[];
  suggestion_prompts?: string[] | null;
  model_selection?: AgentModelSelection | null;
  security_overrides?: Record<string, unknown> | null;
  prompt_mode?: 'full' | 'lean' | 'naked';
  personality_style?: string;
  subagent_ids?: string[];
  max_iterations?: number | null;
  workspace_policy?: WorkspacePolicy;
  engine_params?: Record<string, unknown> | null;
  openapi_services?: OpenAPIServiceConfig[];
  memory_decay_profile?: 'permanent' | 'normal' | 'fast';
  session_policy?: AgentSessionPolicy | null;
  command_bindings?: CommandBindingConfig[] | null;
  notify_targets?: NotifyTarget[] | null;
  tool_gateway_config?: ToolGatewayConfigDTO | null;
  allow_discovery?: boolean;
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

export interface AgentSecretCreate {
  key_name: string;
  secret_value: string;
}

export interface AgentSecretResponse {
  agent_id: string;
  key_name: string;
  created_at: string;
  updated_at: string;
}

export interface AgentProfileSnapshotItem {
  id: string;
  agent_id: string;
  reason: string | null;
  snapshot_data: Record<string, unknown>;
  created_at: string;
}

/**
 * 获取智能体密钥列表
 */
export async function listAgentSecrets(agentId: string): Promise<string[]> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/secrets`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to list agent secrets: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data;
}

/**
 * 创建或更新智能体密钥
 */
export async function createOrUpdateAgentSecret(
  agentId: string,
  data: AgentSecretCreate,
): Promise<AgentSecretResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/secrets`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Failed to save agent secret: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data;
}

/**
 * 删除智能体密钥
 */
export async function deleteAgentSecret(agentId: string, keyName: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/secrets/${keyName}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (response.status === 404) return;
  if (!response.ok) {
    throw new Error(`Failed to delete agent secret: ${response.statusText}`);
  }
}

/**
 * 回滚智能体配置到最近一次快照
 */
export async function rollbackAgentProfile(agentId: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/rollback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    const error: Error & { response?: { status: number } } = new Error(
      `Failed to rollback agent profile: ${response.statusText}`,
    );
    error.response = { status: response.status };
    throw error;
  }
}

/**
 * 回滚智能体配置到指定快照
 */
export async function rollbackAgentProfileToSnapshot(agentId: string, snapshotId: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/rollback/${snapshotId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to rollback agent profile: ${response.statusText}`);
  }
}

/**
 * 获取智能体配置快照列表
 */
export async function listAgentSnapshots(agentId: string): Promise<AgentProfileSnapshotItem[]> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/snapshots`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`Failed to list agent snapshots: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data as AgentProfileSnapshotItem[];
}

export async function listAgents(
  page: number = 1,
  pageSize: number = AGENT_LIST_BUILTIN_PAGE_SIZE,
): Promise<AgentListResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents?page=${page}&page_size=${pageSize}`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to list agents: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data;
}

/**
 * 获取单个智能体详情
 */
export async function getAgent(agentId: string, showSystemPrompt: boolean = false): Promise<Agent> {
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
  });

  if (!response.ok) {
    const error: any = new Error(`Failed to get agent: ${response.statusText}`);
    error.response = { status: response.status };
    throw error;
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
    throw new Error(`Failed to create agent: ${response.statusText}`);
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
    throw new Error(`Failed to update agent: ${response.statusText}`);
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

  if (response.status === 404) return;
  if (!response.ok) {
    throw new Error(`Failed to delete agent: ${response.statusText}`);
  }
}

/**
 * 导出智能体配置（单体返回 AgentCreate 结构，团队返回 {_export_version, leader, members} 结构）
 */
export async function exportAgent(agentId: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/export`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to export agent: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data;
}

/**
 * 导入智能体配置（支持单体和团队两种导出格式）
 */
export async function importAgent(agentData: AgentCreate | Record<string, unknown>): Promise<Agent> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/import`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(agentData),
  });

  if (!response.ok) {
    throw new Error(`Failed to import agent: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data;
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
    throw new Error(`Failed to clone agent: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data;
}

// ============================================================================
// OpenAPI Service API
// ============================================================================

export interface ParsedEndpoint {
  operation_id: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  tags: string[];
  parameters: Record<string, unknown>[];
  request_body_schema: Record<string, unknown> | null;
}

export interface ParseSpecResponse {
  title: string;
  version: string;
  description: string;
  base_url: string;
  spec_version: string;
  endpoints: ParsedEndpoint[];
  tags: Record<string, string>;
  endpoint_count: number;
}

export interface SaaSPreset {
  name: string;
  description: string;
  spec_url: string;
  auth_type: string;
  icon_url?: string;
  selected_endpoints?: string[];
}

export async function getSaaSPresets(): Promise<SaaSPreset[]> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/openapi-services/presets`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch presets: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data ?? result;
}

export async function parseOpenAPISpec(params: {
  spec_url?: string;
  spec_content?: string;
}): Promise<ParseSpecResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/openapi-services/parse-spec`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to parse spec: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data ?? result;
}

export async function testOpenAPIRequest(params: {
  url: string;
  method: string;
  headers?: Record<string, string>;
  body?: unknown;
  timeout_seconds?: number;
}): Promise<{ status_code: number; headers: Record<string, string>; body: string; elapsed_ms: number }> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/openapi-services/test-request`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Test request failed: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data ?? result;
}

export interface ActiveSession {
  chatId: string;
  agentType: string;
  elapsedSeconds: number;
}

export interface ActiveSessionsResponse {
  activeSessions: ActiveSession[];
  maxConcurrent: number;
  availableSlots: number;
}

export async function getActiveSessions(): Promise<ActiveSessionsResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/active-sessions`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch active sessions: ${response.statusText}`);
  }

  const json = await response.json();
  return json.data;
}

// ============================================================================
// Templates API
// ============================================================================

export interface TeamMemberBrief {
  role: string;
  name: string;
  description?: string;
}

export interface TemplateListItem {
  id: string;
  name: string;
  description?: string;
  avatar_url?: string;
  agent_type: string;
  members?: TeamMemberBrief[];
  use_cases?: string[];
}

export async function getTemplates(): Promise<TemplateListItem[]> {
  return apiRequest<TemplateListItem[]>('/agents/templates', { method: 'GET', silent: true });
}

export async function instantiateTemplate(templateId: string): Promise<Agent> {
  return apiRequest<Agent>(`/agents/instantiate-template/${templateId}`, {
    method: 'POST',
    silent: true,
  });
}
