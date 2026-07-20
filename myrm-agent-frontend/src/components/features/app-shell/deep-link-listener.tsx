'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { useFlowPadStore } from '@/store/useFlowPadStore';

/**
 * [POS] Global Deep Link Listener.
 * Mounts at the root layout. Handles deep links from Tauri runtime; web /intent/* dispatch is handled by app routes.
 */
export default function DeepLinkListener() {
  const router = useRouter();
  const openFlowPad = useFlowPadStore((s) => s.open);

  useEffect(() => {
    // Check if we are running in Tauri
    const isTauri = typeof window !== 'undefined' && window.__TAURI_INTERNALS__ !== undefined;

    const dispatcher = new IntentDispatcher(router, openFlowPad);

    if (isTauri) {
      // 1. Handle cold start and hot start deep links via official plugin
      let unlisten: (() => void) | undefined;

      const setupDeepLink = async () => {
        try {
          // Dynamic import keeps Tauri-only APIs out of SSR evaluation.
          const { onOpenUrl } = await import('@tauri-apps/plugin-deep-link');
          unlisten = await onOpenUrl((urls) => {
            console.log('[DeepLinkListener] Received URLs from Tauri:', urls);
            urls.forEach((url) => dispatcher.dispatch(url));
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
      };
    } else {
      // 2. Web/SaaS mode: /intent/* routes are handled by dedicated pages.
      // Keep this listener as a no-op to avoid duplicate dispatches.
    }
  }, [router, openFlowPad]);

  return null;
}
