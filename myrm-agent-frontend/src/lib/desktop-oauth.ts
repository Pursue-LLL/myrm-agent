/**
 * [INPUT]
 * - `@/lib/auth-redirect`::sanitizeAuthRedirectPath (POS: open-redirect guard for in-app paths)
 *
 * [OUTPUT]
 * - beginDesktopOAuth: record a pending sign-in (state + PKCE verifier) and build the `redirect` value and
 *   S256 `codeChallenge` handed to the control plane
 * - consumeDesktopOAuth: validate a returning `state` against the pending sign-in, then drop it (one-shot, TTL-bound)
 * - parseDesktopReturn: read `desktop`/`state` back out of the callback page's `redirect` param
 * - buildDesktopDeepLink: `myrmagent://oauth/callback` URL carrying the one-time exchange id
 *
 * [POS]
 * Contract between the desktop shell and the hosted OAuth callback page. The control plane returns the
 * `redirect` it was given as a query *value*, so desktop markers live inside it rather than at top level.
 * The PKCE verifier never leaves this device until the exchange is redeemed, so a different app registered
 * for the same custom scheme cannot redeem an exchange id it intercepted.
 * Pure browser-storage logic; no React.
 */

import { sanitizeAuthRedirectPath } from '@/lib/auth-redirect';

export const CLOUD_OAUTH_PENDING_KEY = 'myrm-cloud-oauth-pending';
/** Time the user has to finish the browser sign-in and click through to the desktop app. */
export const DESKTOP_OAUTH_TTL_MS = 5 * 60 * 1000;

const CALLBACK_PATH = '/auth/oauth/callback';
const STATE_BYTES = 16;
const VERIFIER_BYTES = 32;
const MAX_STATE_LENGTH = 128;

interface PendingDesktopOAuth {
  cpBaseUrl: string;
  state: string;
  codeVerifier: string;
  createdAt: number;
}

/** What a validated pending sign-in hands to the exchange redemption. */
export interface DesktopOAuthSession {
  cpBaseUrl: string;
  codeVerifier: string;
}

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytes;
}

function toBase64Url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

async function s256Challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return toBase64Url(new Uint8Array(digest));
}

function readPending(): PendingDesktopOAuth | null {
  try {
    const raw = window.localStorage.getItem(CLOUD_OAUTH_PENDING_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<PendingDesktopOAuth>;
    if (
      typeof parsed.cpBaseUrl === 'string' &&
      parsed.cpBaseUrl &&
      typeof parsed.state === 'string' &&
      parsed.state &&
      typeof parsed.codeVerifier === 'string' &&
      parsed.codeVerifier &&
      typeof parsed.createdAt === 'number'
    ) {
      return {
        cpBaseUrl: parsed.cpBaseUrl.replace(/\/+$/, ''),
        state: parsed.state,
        codeVerifier: parsed.codeVerifier,
        createdAt: parsed.createdAt,
      };
    }
  } catch {
    // 损坏的待决记录等同于没有
  }
  return null;
}

/**
 * Records a new pending sign-in (replacing any previous one) and returns the `redirect` value plus the S256
 * `codeChallenge` for the control plane. Throws when `cpBaseUrl` is not an http(s) URL or SHA-256 is
 * unavailable; nothing is stored in that case.
 */
export async function beginDesktopOAuth(
  cpBaseUrl: string,
  now: number = Date.now(),
): Promise<{ redirect: string; codeChallenge: string }> {
  const base = cpBaseUrl.replace(/\/+$/, '');
  if (!/^https?:$/.test(new URL(base).protocol)) {
    throw new Error('Control plane URL must be http(s)');
  }
  const state = toHex(randomBytes(STATE_BYTES));
  const codeVerifier = toBase64Url(randomBytes(VERIFIER_BYTES));
  const codeChallenge = await s256Challenge(codeVerifier);
  const pending: PendingDesktopOAuth = { cpBaseUrl: base, state, codeVerifier, createdAt: now };
  window.localStorage.setItem(CLOUD_OAUTH_PENDING_KEY, JSON.stringify(pending));
  return { redirect: `${CALLBACK_PATH}?desktop=1&state=${state}`, codeChallenge };
}

/**
 * Returns the pending sign-in when `state` matches and is still fresh, and drops it (one-shot). A wrong `state`
 * leaves the record alone so a forged link cannot cancel the user's real sign-in; an expired record is dropped.
 */
export function consumeDesktopOAuth(state: string, now: number = Date.now()): DesktopOAuthSession | null {
  const pending = readPending();
  if (!pending || now - pending.createdAt > DESKTOP_OAUTH_TTL_MS) {
    window.localStorage.removeItem(CLOUD_OAUTH_PENDING_KEY);
    return null;
  }
  if (pending.state !== state) {
    return null;
  }
  window.localStorage.removeItem(CLOUD_OAUTH_PENDING_KEY);
  return { cpBaseUrl: pending.cpBaseUrl, codeVerifier: pending.codeVerifier };
}

/** Extracts the desktop state from the `redirect` query value the control plane handed back. */
export function parseDesktopReturn(redirectParam: string | null): { state: string } | null {
  const path = sanitizeAuthRedirectPath(redirectParam);
  if (!path) {
    return null;
  }
  const url = new URL(path, 'http://local.invalid');
  const state = url.searchParams.get('state');
  if (url.pathname !== CALLBACK_PATH || url.searchParams.get('desktop') !== '1' || !state) {
    return null;
  }
  return state.length <= MAX_STATE_LENGTH ? { state } : null;
}

export function buildDesktopDeepLink(exchange: string, state: string): string {
  const params = new URLSearchParams({ exchange, state });
  return `myrmagent://oauth/callback?${params.toString()}`;
}
