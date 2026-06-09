/**
 * Browser Extension Bridge API service.
 *
 * [INPUT]
 * - @/lib/api::apiRequest, getApiUrl
 *
 * [OUTPUT]
 * - getExtensionStatus: Fetch current extension connection status
 * - getAuthorizedDomains: Fetch authorized domain list
 * - updateAuthorizedDomains: Update authorized domain list
 * - listExtensionTabs: List available tabs from extension
 * - disconnectExtension: Manually disconnect extension
 *
 * [POS]
 * API service layer for browser extension bridge management.
 */

import { apiRequest, getApiUrl } from '@/lib/api';

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
