/**
 * Route → readability scene SSOT (immersive chat vs functional work pages).
 * Keep in sync with `theme-pre-init-script.ts` / `public/theme-init.js`.
 */

import type { ThemeReadabilityScene } from './schema';

/** Paths that always use immersive wallpaper readability. */
export const IMMERSIVE_EXACT_PATHS = ['/', '/chat'] as const;

/**
 * Functional route prefixes — aligned with `app/_ARCH.md` feature pages.
 * Single-segment chat sessions (`/[chatId]`) are immersive unless listed here.
 */
export const FUNCTIONAL_ROUTE_PREFIXES = [
  '/kanban',
  '/settings',
  '/projects',
  '/eval-lab',
  '/brain',
  '/library',
  '/artifacts',
  '/cron',
  '/work',
  '/workspace',
  '/audit',
  '/security',
  '/agents',
  '/canvas',
  '/batch-optimization',
  '/skill-optimization',
  '/journey',
  '/subscription',
  '/pricing',
  '/health',
  '/mobile',
  '/auth',
  '/payment',
  '/growth',
] as const;

/** First URL segment names for static App Router pages (excludes dynamic `[chatId]`). */
export const STATIC_APP_SEGMENTS = new Set<string>([
  'agents',
  'audit',
  'artifacts',
  'auth',
  'batch-optimization',
  'brain',
  'canvas',
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
  'security',
  'settings',
  'skill-optimization',
  'subscription',
  'workspace',
  'kanban',
  'cron',
  'work',
]);

function normalizePathname(pathname: string): string {
  const withoutQuery = pathname.split('?')[0] ?? pathname;
  if (withoutQuery.length > 1 && withoutQuery.endsWith('/')) {
    return withoutQuery.slice(0, -1);
  }
  return withoutQuery || '/';
}

function matchesFunctionalPrefix(normalized: string): boolean {
  return FUNCTIONAL_ROUTE_PREFIXES.some((prefix) => normalized === prefix || normalized.startsWith(`${prefix}/`));
}

function isChatSessionPath(normalized: string): boolean {
  const match = /^\/([^/]+)$/.exec(normalized);
  if (!match) {
    return false;
  }
  return !STATIC_APP_SEGMENTS.has(match[1]);
}

export function resolveReadabilityScene(pathname: string): ThemeReadabilityScene {
  const normalized = normalizePathname(pathname);
  if ((IMMERSIVE_EXACT_PATHS as readonly string[]).includes(normalized)) {
    return 'immersive';
  }
  if (matchesFunctionalPrefix(normalized)) {
    return 'functional';
  }
  if (isChatSessionPath(normalized)) {
    return 'immersive';
  }
  return 'functional';
}
