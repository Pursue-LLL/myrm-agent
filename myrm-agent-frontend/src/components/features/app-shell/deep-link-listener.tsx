'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { useFlowPadStore } from '@/store/useFlowPadStore';

/**
 * [POS] Global Deep Link Listener.
 * Mounts at the root layout. Listens for deep links from Tauri or Web and dispatches them.
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
          // [Bugfix] 动态导入 Tauri API，防止 SSR 崩溃
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
      // 2. Web/SaaS mode: Check if the current URL is an intent URL
      // This is handled by Next.js routing naturally, but if we want to intercept
      // specific patterns on mount, we can do it here.
      // For now, Next.js pages will handle /intent/... routes directly,
      // or we can parse window.location.href here if needed.
      const currentUrl = window.location.href;
      if (currentUrl.includes('/intent/')) {
        dispatcher.dispatch(currentUrl);
      }
    }
  }, [router, openFlowPad]);

  return null;
}
