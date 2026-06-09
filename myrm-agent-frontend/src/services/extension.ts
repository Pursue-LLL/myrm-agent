/**
 * [INPUT]
 * - @/lib/api::apiRequest, getApiUrl, getWsUrl (POS: 前端 API 接入层)
 * - @/lib/deploy-mode::getBackendBaseUrl (POS: 前端部署模式与基础地址解析层)
 *
 * [OUTPUT]
 * - getExtensionStatus: Fetch current extension connection status
 * - getAuthorizedDomains: Fetch authorized domain list
 * - updateAuthorizedDomains: Update authorized domain list
 * - listExtensionTabs: List available tabs from extension
 * - disconnectExtension: Manually disconnect extension
 * - getExtensionWebSocketUrl: Absolute WS URL for extension popup (all deploy modes)
 * - getExtensionSetupHints: Whether EXTENSION_AUTH_TOKEN is configured
 *
 * [POS]
 * Browser extension bridge API service. Provides data-fetching and URL utilities
 * for the ExtensionBridgeSection Settings UI.
 */

import { apiRequest, getApiUrl, getWsUrl } from '@/lib/api';
import { getBackendBaseUrl } from '@/lib/deploy-mode';

export interface ExtensionTab {
  tab_id: number;
  url: string;
  title: string;
  domain: string;
  active: boolean;
}

export interface ExtensionStatus {
  connected: boolean;
  extension_version: string;
  browser_name: string;
  authorized_domains: string[];
  available_tabs: ExtensionTab[];
}

export interface ExtensionSetupHints {
  auth_token_configured: boolean;
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
  return `${proto}//${window.location.hostname}:25808/api/v1/ws/extension`;
}

export async function getExtensionSetupHints(): Promise<ExtensionSetupHints> {
  const res = await apiRequest(getApiUrl('/extension/setup-hints'));
  return res.json();
}

export async function getExtensionStatus(): Promise<ExtensionStatus> {
  const res = await apiRequest(getApiUrl('/extension/status'));
  return res.json();
}

export async function getAuthorizedDomains(): Promise<{ authorized_domains: string[] }> {
  const res = await apiRequest(getApiUrl('/extension/domains'));
  return res.json();
}

export async function updateAuthorizedDomains(domains: string[]): Promise<{ authorized_domains: string[] }> {
  const res = await apiRequest(getApiUrl('/extension/domains'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domains }),
  });
  return res.json();
}

export async function listExtensionTabs(): Promise<ExtensionTab[]> {
  const res = await apiRequest(getApiUrl('/extension/tabs'));
  return res.json();
}

export async function disconnectExtension(): Promise<void> {
  await apiRequest(getApiUrl('/extension/disconnect'), { method: 'POST' });
}
