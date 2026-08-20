/**
 * [INPUT]
 * - lib/cp-base-url::resolveCpBaseUrl (POS: CP REST base URL for browser)
 * - lib/auth-cp-token::isCpAuthTokenValid (POS: CP HMAC API token client decode)
 *
 * [OUTPUT]
 * - probeCpHealth, hasCpMarketplaceJwt, resolveThemeMarketplaceGateState
 *
 * [POS]
 * Theme marketplace availability SSOT (CP health + cloud auth token). Used by Theme Studio Gallery/Creator/Admin.
 */

import { isCpAuthTokenValid } from '@/lib/auth-cp-token';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';

const LOCAL_ONLY_AUTH_TOKEN = 'local_user_token';

export type ThemeMarketplaceGateState = 'loading' | 'ready' | 'needs_auth' | 'offline';

export function readAuthToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const token = window.localStorage.getItem('auth_token')?.trim();
  return token || null;
}

/** True when the browser holds a non-expired CP HMAC API token (Gallery/Creator API auth). */
export function hasCpMarketplaceJwt(token: string | null = readAuthToken()): boolean {
  if (!token || token === LOCAL_ONLY_AUTH_TOKEN) {
    return false;
  }
  return isCpAuthTokenValid(token);
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

export async function resolveThemeMarketplaceGateState(): Promise<Exclude<ThemeMarketplaceGateState, 'loading'>> {
  const cpUp = await probeCpHealth();
  if (!cpUp) {
    return 'offline';
  }
  return hasCpMarketplaceJwt() ? 'ready' : 'needs_auth';
}
