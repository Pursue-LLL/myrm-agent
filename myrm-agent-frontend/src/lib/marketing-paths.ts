/** Tauri transparent popped-out desk pet — no AppLayout chrome. */
export const PET_OVERLAY_PATH = '/pet-overlay';

/** Routes that render without AppLayout sidebar (public + auth + billing + pet overlay). */
export const STANDALONE_PATHS = [
  '/pricing',
  '/auth/login',
  '/auth/setup',
  '/auth/oauth/callback',
  '/payment/success',
  '/payment/cancel',
  PET_OVERLAY_PATH,
] as const;

export function isPetOverlayPath(pathname: string): boolean {
  return pathname === PET_OVERLAY_PATH || pathname.startsWith(`${PET_OVERLAY_PATH}/`);
}

export function isStandalonePath(pathname: string): boolean {
  return (
    isPetOverlayPath(pathname) ||
    STANDALONE_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))
  );
}

/** Routes accessible without authentication in SaaS (sandbox) mode. */
export const SAAS_PUBLIC_PATHS = [
  '/pricing',
  '/auth/login',
  '/auth/setup',
  '/auth/oauth/callback',
  '/payment/success',
  '/payment/cancel',
] as const;

export function isSaasPublicPath(pathname: string): boolean {
  return SAAS_PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}
