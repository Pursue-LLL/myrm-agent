/**
 * [INPUT]
 * - W3C URL API (same-origin checks against Service Worker `location.origin`)
 *
 * [OUTPUT]
 * - sanitizePushTargetUrl, chatIdFromPushPath, resolvePushClientFocusAction
 * - SETTINGS_PATH_PREFIX, RESERVED_APP_SEGMENTS
 *
 * [POS]
 * Pure helpers for Web Push click-through URL sanitization and client focus routing.
 * Imported by src/app/sw.ts; bundled via scripts/build-sw-src.mjs before inject-manifest.
 */

/** Top-level App Router segments that must not be treated as chat deep links. */
// SSOT: keep in sync with reserved first segments in src/app/_ARCH.md route table.
export const SETTINGS_PATH_PREFIX = '/settings/';

export const RESERVED_APP_SEGMENTS = new Set([
  'agents',
  'artifacts',
  'audit',
  'batch-optimization',
  'brain',
  'chat',
  'eval-lab',
  'growth',
  'health',
  'journey',
  'library',
  'mobile',
  'payment',
  'pricing',
  'projects',
  'research',
  'security',
  'settings',
  'skill-optimization',
  'subscription',
  'work',
  'workspace',
]);

export type PushClientFocusAction = 'focus' | 'navigate';

export function sanitizePushTargetUrl(rawUrl: string, origin: string): string {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl, origin);
  } catch {
    return '/';
  }

  if (parsed.origin !== origin) {
    return '/';
  }

  const pathname = parsed.pathname;
  if (pathname === '/') {
    return '/';
  }

  if (pathname.startsWith(SETTINGS_PATH_PREFIX)) {
    return `${pathname}${parsed.search}`;
  }

  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 1 && !RESERVED_APP_SEGMENTS.has(segments[0])) {
    const chatId = segments[0];
    if (chatId.length >= 8 && /^[a-zA-Z0-9_-]+$/.test(chatId)) {
      return `/${chatId}${parsed.search}`;
    }
  }

  return '/';
}

export function chatIdFromPushPath(pathname: string): string | null {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length !== 1 || RESERVED_APP_SEGMENTS.has(segments[0])) {
    return null;
  }
  const chatId = segments[0];
  if (chatId.length < 8 || !/^[a-zA-Z0-9_-]+$/.test(chatId)) {
    return null;
  }
  return chatId;
}

/**
 * When a window client already matches the target pathname, decide whether to
 * focus in place or navigate (e.g. append ?approval= query on an open chat tab).
 */
export function resolvePushClientFocusAction(
  clientUrl: string,
  sanitizedTargetUrl: string,
  origin: string,
): PushClientFocusAction | null {
  let client: URL;
  let target: URL;
  try {
    client = new URL(clientUrl);
    target = new URL(sanitizedTargetUrl, origin);
  } catch {
    return null;
  }

  if (client.origin !== target.origin || client.pathname !== target.pathname) {
    return null;
  }

  if (client.search === target.search) {
    return 'focus';
  }

  return 'navigate';
}
