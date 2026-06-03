/** Routes that render without AppLayout sidebar (public + auth + billing). */
export const STANDALONE_PATHS = [
  '/pricing',
  '/auth/login',
  '/auth/setup',
  '/auth/oauth/callback',
  '/auth/mcp-callback',
  '/payment/success',
  '/payment/cancel',
] as const;

export function isStandalonePath(pathname: string): boolean {
  return STANDALONE_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

/** Routes accessible without authentication in SaaS (sandbox) mode. */
export const SAAS_PUBLIC_PATHS = [
  '/pricing',
  '/auth/login',
  '/auth/setup',
  '/auth/oauth/callback',
  '/auth/mcp-callback',
  '/payment/success',
  '/payment/cancel',
] as const;

export function isSaasPublicPath(pathname: string): boolean {
  return SAAS_PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}
