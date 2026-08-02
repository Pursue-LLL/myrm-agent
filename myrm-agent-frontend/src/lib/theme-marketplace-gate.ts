/**
 * Theme marketplace availability — CP health + cloud JWT (not local-only token).
 */

import { resolveCpBaseUrl } from '@/lib/cp-base-url';

const LOCAL_ONLY_AUTH_TOKEN = 'local_user_token';

export type ThemeMarketplaceGateState =
  | 'loading'
  | 'ready'
  | 'needs_auth'
  | 'offline';

export function readAuthToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const token = window.localStorage.getItem('auth_token')?.trim();
  return token || null;
}

/** True when the browser holds a CP-issued JWT (Gallery/Creator API auth). */
export function hasCpMarketplaceJwt(token: string | null = readAuthToken()): boolean {
  if (!token || token === LOCAL_ONLY_AUTH_TOKEN) {
    return false;
  }
  return token.split('.').length === 3;
}

export async function probeCpHealth(baseUrl: string = resolveCpBaseUrl()): Promise<boolean> {
  const url = `${baseUrl.replace(/\/+$/, '')}/api/health`;
  try {
    const response = await fetch(url, { method: 'GET', cache: 'no-store' });
    return response.ok;
  } catch {
    return false;
  }
}

export async function resolveThemeMarketplaceGateState(): Promise<
  Exclude<ThemeMarketplaceGateState, 'loading'>
> {
  const cpUp = await probeCpHealth();
  if (!cpUp) {
    return 'offline';
  }
  return hasCpMarketplaceJwt() ? 'ready' : 'needs_auth';
}
