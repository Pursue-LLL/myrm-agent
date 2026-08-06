/**
 * [INPUT]
 * - @/lib/api::apiRequest, getWsUrl (POS: 前端 API 接入层)
 * - @/lib/deploy-mode::getBackendBaseUrl (POS: 前端部署模式与基础地址解析层)
 *
 * [OUTPUT]
 * - getExtensionStatus: Fetch current extension connection status
 * - getAuthorizedDomains: Fetch authorized domain list
 * - updateAuthorizedDomains: Update authorized domain list
 * - listExtensionTabs: List available tabs from extension
 * - disconnectExtension: Manually disconnect extension
 * - getExtensionWebSocketUrl: Absolute WS URL for extension popup (all deploy modes)
 * - getExtensionClipAgentConfig / updateExtensionClipAgentConfig: Wiki clip agent scope SSOT
 * - getExtensionSetupHints: Non-secret setup hints (token required/configured + CDP discoverability)
 *
 * [POS]
 * Browser extension bridge API service. REST paths are **relative** (`/extension/...`) for
 * apiRequest — never wrap with getApiUrl() (double /api/v1 prefix → 404). Loopback dev WS
 * fallback uses port 8080 via isLoopbackDevHost().
 */

import { apiRequest, getWsUrl } from '@/lib/api';
import { getBackendBaseUrl, isLoopbackDevHost } from '@/lib/deploy-mode';

export interface ExtensionTab {
  tab_id: number;
  url: string;
  title: string;
  domain: string;
  active: boolean;
}

export interface ExtensionStatus {
  connected: boolean;
  handshake_ready: boolean;
  extension_version: string;
  browser_name: string;
  authorized_domains: string[];
  capabilities: string[];
  available_tabs: ExtensionTab[];
}

export interface ExtensionSetupHints {
  auth_token_configured: boolean;
  auth_token_required: boolean;
  cdp_endpoint_discovered: boolean;
}

export interface DomainPolicyWarning {
  code: 'wildcard_includes_root';
  pattern: string;
  root_domain: string;
}

export interface ExtensionClipAgentConfig {
  agent_id: string | null;
  web_ui_origin: string | null;
}

/**
 * Absolute WebSocket URL for the MV3 extension popup to copy.
 * Unlike getWsUrl (which may return a relative path in Local mode for in-app use),
 * this always returns a fully qualified ws(s):// URL because the extension popup
 * runs in an independent context and cannot resolve relative paths.
 */
export function getExtensionWebSocketUrl(): string {
  const wsUrl = getWsUrl('/ws/extension');
  if (/^wss?:\/\//.test(wsUrl)) {
    return wsUrl;
  }
  if (typeof window === 'undefined') {
    return wsUrl;
  }
  const backendBase = getBackendBaseUrl();
  if (backendBase) {
    return backendBase.replace(/^http/, 'ws') + '/api/v1/ws/extension';
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const port = isLoopbackDevHost() ? 8080 : 25808;
  return `${proto}//${window.location.hostname}:${port}/api/v1/ws/extension`;
}

export async function getExtensionSetupHints(): Promise<ExtensionSetupHints> {
  return apiRequest<ExtensionSetupHints>('/extension/setup-hints');
}

export async function getExtensionStatus(): Promise<ExtensionStatus> {
  return apiRequest<ExtensionStatus>('/extension/status');
}

export async function getAuthorizedDomains(): Promise<{ authorized_domains: string[]; warnings: DomainPolicyWarning[] }> {
  return apiRequest<{ authorized_domains: string[]; warnings: DomainPolicyWarning[] }>('/extension/domains');
}

export async function updateAuthorizedDomains(
  domains: string[],
): Promise<{ authorized_domains: string[]; warnings: DomainPolicyWarning[] }> {
  return apiRequest<{ authorized_domains: string[]; warnings: DomainPolicyWarning[] }>('/extension/domains', {
    method: 'PUT',
    body: JSON.stringify({ domains }),
  });
}

export async function listExtensionTabs(): Promise<ExtensionTab[]> {
  return apiRequest<ExtensionTab[]>('/extension/tabs');
}

export async function disconnectExtension(): Promise<void> {
  await apiRequest('/extension/disconnect', { method: 'POST' });
}

export async function getExtensionClipAgentConfig(): Promise<ExtensionClipAgentConfig> {
  return apiRequest<ExtensionClipAgentConfig>('/extension/clip-agent');
}

export async function updateExtensionClipAgentConfig(
  agentId: string | null,
  webUiOrigin: string | null,
): Promise<ExtensionClipAgentConfig> {
  return apiRequest<ExtensionClipAgentConfig>('/extension/clip-agent', {
    method: 'PUT',
    body: JSON.stringify({ agent_id: agentId, web_ui_origin: webUiOrigin }),
  });
}
