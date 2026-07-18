import { defaultCache } from '@serwist/next/worker';
import type { PrecacheEntry } from '@serwist/precaching';
import { installSerwist } from '@serwist/sw';
import { ExpirationPlugin, NetworkFirst } from 'serwist';

import {
  chatIdFromPushPath,
  resolvePushClientFocusAction,
  sanitizePushTargetUrl,
} from '../lib/web-push/pushTargetUrl';

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

interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
}

self.addEventListener('push', (event: PushEvent) => {
  if (!event.data) return;

  let payload: PushPayload = {};
  try {
    payload = event.data.json() as PushPayload;
  } catch {
    payload = { title: 'Myrm AI', body: event.data.text() };
  }

  const origin = self.location.origin;
  const safeUrl = sanitizePushTargetUrl(payload.url || '/', origin);
  const chatId = chatIdFromPushPath(new URL(safeUrl, origin).pathname);
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

  const origin = self.location.origin;
  const rawTargetUrl = (event.notification.data as { url?: string })?.url || '/';
  const targetUrl = sanitizePushTargetUrl(rawTargetUrl, origin);

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        const action = resolvePushClientFocusAction(client.url, targetUrl, origin);
        if (action === 'focus' && 'focus' in client) {
          return client.focus();
        }
        if (action === 'navigate' && 'navigate' in client) {
          return client.navigate(targetUrl);
        }
      }
      return self.clients.openWindow(targetUrl);
    }),
  );
});
