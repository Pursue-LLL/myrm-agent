import { chatIdFromPushPath, resolvePushClientFocusAction, sanitizePushTargetUrl } from '../lib/web-push/pushTargetUrl';

declare const self: ServiceWorkerGlobalScope;

/**
 * [INPUT]
 * - lib/web-push/pushTargetUrl (POS: Web Push click-through URL sanitization and client focus routing)
 * - Push payload JSON from WebPushDispatcher (`title`, `body`, `url`)
 *
 * [OUTPUT]
 * - Web Push notification display + notificationclick focus / navigate / open
 * - Immediate takeover of open tabs; every Cache Storage entry is dropped on activation
 *
 * [POS]
 * Web Push service worker, registered at `/sw.js` with the default scope. It has no fetch handler and
 * keeps no caches: page loads and API calls always go to the network.
 */

self.addEventListener('install', (event: ExtendableEvent) => {
  event.waitUntil(self.skipWaiting());
});

/** This worker caches nothing, so whatever sits in Cache Storage under this origin is stale. */
async function clearCacheStorage(): Promise<void> {
  const names = await caches.keys();
  await Promise.allSettled(names.map((name) => caches.delete(name)));
}

self.addEventListener('activate', (event: ExtendableEvent) => {
  // Clearing is best effort: a storage error must not keep the worker from taking over.
  event.waitUntil(Promise.all([clearCacheStorage().catch(() => undefined), self.clients.claim()]));
});

interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
}

self.addEventListener('push', (event: PushEvent) => {
  if (!event.data) {
    return;
  }

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
