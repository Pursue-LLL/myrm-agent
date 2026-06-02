/** Lightweight session marker for Next.js middleware (localStorage is unavailable server-side). */
export const AUTH_SESSION_COOKIE = 'myrm_auth';

const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export function setAuthSessionCookie(): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${AUTH_SESSION_COOKIE}=1; path=/; max-age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
}

export function clearAuthSessionCookie(): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${AUTH_SESSION_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}
