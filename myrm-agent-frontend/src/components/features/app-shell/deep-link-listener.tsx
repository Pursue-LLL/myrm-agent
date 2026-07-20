'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { useFlowPadStore } from '@/store/useFlowPadStore';

/**
 * [POS] Global Deep Link Listener.
 * Mounts at the root layout. Handles deep links from Tauri runtime with ordered + deduplicated dispatch.
 * Failed single-url dispatches are isolated so the queue can continue and retry later.
 * Web /intent/* dispatch is handled by app routes.
 */
export default function DeepLinkListener() {
  const router = useRouter();
  const openFlowPad = useFlowPadStore((s) => s.open);
  const dispatchQueueRef = useRef<Promise<void>>(Promise.resolve());
  const recentDispatchRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    // Check if we are running in Tauri
    const isTauri = typeof window !== 'undefined' && window.__TAURI_INTERNALS__ !== undefined;

    const dispatcher = new IntentDispatcher(router, openFlowPad);

    if (isTauri) {
      // 1. Handle cold start and hot start deep links via official plugin
      let unlisten: (() => void) | undefined;
      const DEDUPE_WINDOW_MS = 3_000;

      const enqueueDeepLinks = (urls: string[]) => {
        const now = Date.now();
        for (const [url, ts] of recentDispatchRef.current.entries()) {
          if (now - ts > DEDUPE_WINDOW_MS) {
            recentDispatchRef.current.delete(url);
          }
        }
        const uniqueUrls = urls.filter((url) => {
          if (recentDispatchRef.current.has(url)) {
            return false;
          }
          recentDispatchRef.current.set(url, now);
          return true;
        });
        if (uniqueUrls.length === 0) {
          return;
        }
        dispatchQueueRef.current = dispatchQueueRef.current
          .catch(() => undefined)
          .then(async () => {
            for (const url of uniqueUrls) {
              try {
                await dispatcher.dispatch(url);
              } catch (error) {
                // Allow immediate retry for failed dispatches instead of keeping them deduped.
                recentDispatchRef.current.delete(url);
                console.error('[DeepLinkListener] Failed to dispatch deep link:', url, error);
              }
            }
          });
      };

      const setupDeepLink = async () => {
        try {
          // Dynamic import keeps Tauri-only APIs out of SSR evaluation.
          const { onOpenUrl } = await import('@tauri-apps/plugin-deep-link');
          unlisten = await onOpenUrl((urls) => {
            console.log('[DeepLinkListener] Received URLs from Tauri:', urls);
            enqueueDeepLinks(urls);
          });
          console.log('[DeepLinkListener] Successfully registered Tauri deep link handler');
        } catch (error) {
          console.error('[DeepLinkListener] Failed to register Tauri deep link handler:', error);
        }
      };

      setupDeepLink();

      return () => {
        if (unlisten) {
          unlisten();
        }
        recentDispatchRef.current.clear();
        dispatchQueueRef.current = Promise.resolve();
      };
    } else {
      // 2. Web/SaaS mode: /intent/* routes are handled by dedicated pages.
      // Keep this listener as a no-op to avoid duplicate dispatches.
    }
  }, [router, openFlowPad]);

  return null;
}
