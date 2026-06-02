/**
 * [INPUT]
 * - URL redirect query from middleware or marketing deep links
 *
 * [OUTPUT]
 * - sanitizeAuthRedirectPath: safe internal path for post-login navigation
 * - readAuthRedirectParam: read `redirect` from URLSearchParams
 *
 * [POS]
 * Post-auth navigation guard; blocks open redirects while preserving query strings.
 */

const REDIRECT_PARAM = 'redirect';

/** Allowed internal path after login (must start with `/`, no protocol/host). */
export function sanitizeAuthRedirectPath(raw: string | null | undefined): string | null {
  if (!raw || typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return null;
  if (trimmed.includes('://')) return null;
  return trimmed;
}

export function readAuthRedirectParam(searchParams: URLSearchParams): string | null {
  return sanitizeAuthRedirectPath(searchParams.get(REDIRECT_PARAM));
}

export function authRedirectQueryParam(returnPath: string): string {
  const safe = sanitizeAuthRedirectPath(returnPath) ?? '/';
  return `${REDIRECT_PARAM}=${encodeURIComponent(safe)}`;
}

/** Internal login page path with optional post-auth return target. */
export function buildAuthLoginPath(returnPath?: string | null): string {
  const safe = sanitizeAuthRedirectPath(returnPath ?? null);
  if (!safe || safe === '/') {
    return '/auth/login';
  }
  return `/auth/login?${authRedirectQueryParam(safe)}`;
}
