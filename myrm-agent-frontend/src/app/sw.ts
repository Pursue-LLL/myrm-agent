import { defaultCache } from '@serwist/next/worker';
import type { PrecacheEntry } from '@serwist/precaching';
import { installSerwist } from '@serwist/sw';
import { ExpirationPlugin, NetworkFirst } from 'serwist';

declare const self: WorkerGlobalScope & {
  __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
};

// [POS] Service Worker Runtime Configuration
// Handles precaching of static assets and dynamic caching of API requests.

installSerwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    // 1. Cache the history API (NetworkFirst) to allow offline reading
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
        networkTimeoutSeconds: 5, // Fallback to cache quickly if network is slow
      }),
    },
    // 2. Default Next.js caching strategies (StaleWhileRevalidate for assets, images, etc.)
    ...defaultCache,
  ],
});
