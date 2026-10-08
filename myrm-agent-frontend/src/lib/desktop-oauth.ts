/**
 * [INPUT]
 * - `@/lib/auth-redirect`::sanitizeAuthRedirectPath (POS: open-redirect guard for in-app paths)
 *
 * [OUTPUT]
 * - beginDesktopOAuth: record a pending sign-in and build the `redirect` value handed to the control plane
 * - consumeDesktopOAuth: validate a returning `state` against the pending sign-in (one-shot, TTL-bound)
 * - parseDesktopReturn: read `desktop`/`state` back out of the callback page's `redirect` param
 * - buildDesktopDeepLink: `myrmagent://oauth/callback` URL carrying the one-time exchange id
 *
 * [POS]
 * Contract between the desktop shell and the hosted OAuth callback page. The control plane returns the
 * `redirect` it was given as a query *value*, so desktop markers live inside it rather than at top level.
 * Pure browser-storage logic; no React.
 */

import { sanitizeAuthRedirectPath } from '@/lib/auth-redirect';

export const CLOUD_OAUTH_PENDING_KEY = 'myrm-cloud-oauth-pending';
/** Time the user has to finish the browser sign-in and click through to the desktop app. */
export const DESKTOP_OAUTH_TTL_MS = 5 * 60 * 1000;

const CALLBACK_PATH = '/auth/oauth/callback';
const STATE_BYTES = 16;
const MAX_STATE_LENGTH = 128;

interface PendingDesktopOAuth {
  cpBaseUrl: string;
  state: string;
  createdAt: number;
}

function randomState(): string {
  const bytes = new Uint8Array(STATE_BYTES);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
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
      typeof parsed.createdAt === 'number'
    ) {
      return { cpBaseUrl: parsed.cpBaseUrl.replace(/\/+$/, ''), state: parsed.state, createdAt: parsed.createdAt };
    }
  } catch {
    // 损坏的待决记录等同于没有
  }
  return null;
}

/** Records a new pending sign-in (replacing any previous one) and returns the `redirect` value for the control plane. */
export function beginDesktopOAuth(cpBaseUrl: string, now: number = Date.now()): string {
  const state = randomState();
  const pending: PendingDesktopOAuth = { cpBaseUrl: cpBaseUrl.replace(/\/+$/, ''), state, createdAt: now };
  window.localStorage.setItem(CLOUD_OAUTH_PENDING_KEY, JSON.stringify(pending));
  return `${CALLBACK_PATH}?desktop=1&state=${state}`;
}

/**
 * Consumes the pending sign-in when `state` matches. Returns the control-plane base URL it was started
 * against, or null when nothing valid is waiting. A wrong `state` leaves the record alone so a forged
 * link cannot cancel the user's real sign-in; an expired record is dropped.
 */
export function consumeDesktopOAuth(state: string, now: number = Date.now()): string | null {
  const pending = readPending();
  if (!pending) {
    window.localStorage.removeItem(CLOUD_OAUTH_PENDING_KEY);
    return null;
  }
  if (now - pending.createdAt > DESKTOP_OAUTH_TTL_MS) {
    window.localStorage.removeItem(CLOUD_OAUTH_PENDING_KEY);
    return null;
  }
  if (pending.state !== state) {
    return null;
  }
  window.localStorage.removeItem(CLOUD_OAUTH_PENDING_KEY);
  return pending.cpBaseUrl;
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
