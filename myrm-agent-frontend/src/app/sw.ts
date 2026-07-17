import { defaultCache } from '@serwist/next/worker';
import type { PrecacheEntry } from '@serwist/precaching';
import { installSerwist } from '@serwist/sw';
import { ExpirationPlugin, NetworkFirst } from 'serwist';

declare const self: ServiceWorkerGlobalScope & {
  __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
};

// [POS] Service Worker Runtime Configuration
// Handles precaching of static assets, dynamic caching of API requests,
// and Web Push notification display + click handling.

installSerwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    {
      matcher: ({ url }) => url.pathname.startsWith('/api/v1/chats') || url.pathname.startsWith('/api/v1/agents'),
      handler: new NetworkFirst({
        cacheName: 'myrm-agent-api-cache',
        plugins: [
          new ExpirationPlugin({
            maxEntries: 100,
            maxAgeSeconds: 7 * 24 * 60 * 60,
          }),
        ],
        networkTimeoutSeconds: 5,
      }),
    },
    ...defaultCache,
  ],
});

// --- Web Push Notification Handlers ---

interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
}

const SETTINGS_PATH_PREFIX = '/settings/';

/** Top-level App Router segments that must not be treated as chat deep links. */
const RESERVED_APP_SEGMENTS = new Set([
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

function sanitizePushTargetUrl(rawUrl: string): string {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl, self.location.origin);
  } catch {
    return '/';
  }

  if (parsed.origin !== self.location.origin) {
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

function chatIdFromPushPath(pathname: string): string | null {
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

self.addEventListener('push', (event: PushEvent) => {
  if (!event.data) return;

  let payload: PushPayload = {};
  try {
    payload = event.data.json() as PushPayload;
  } catch {
    payload = { title: 'Myrm AI', body: event.data.text() };
  }

  const safeUrl = sanitizePushTargetUrl(payload.url || '/');
  const chatId = chatIdFromPushPath(new URL(safeUrl, self.location.origin).pathname);
  const title = payload.title || 'Myrm AI';
  const options: NotificationOptions = {
    body: payload.body || '',
    icon: '/favicon-32.png',
    badge: '/favicon-32.png',
    data: { url: safeUrl },
    tag: chatId ? `myrm-${chatId}` : `myrm-${Date.now()}`,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();

  const rawTargetUrl = (event.notification.data as { url?: string })?.url || '/';
  const targetUrl = sanitizePushTargetUrl(rawTargetUrl);
  const targetPathname = new URL(targetUrl, self.location.origin).pathname;

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (new URL(client.url).pathname === targetPathname && 'focus' in client) {
          return client.focus();
        }
      }
      return self.clients.openWindow(targetUrl);
    }),
  );
});
