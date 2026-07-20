'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { useFlowPadStore } from '@/store/useFlowPadStore';

/**
 * Web/SaaS deep-link landing page.
 * Handles /intent/* URLs that are not part of normal app routes.
 */
export default function IntentPage() {
  const router = useRouter();
  const openFlowPad = useFlowPadStore((state) => state.open);

  useEffect(() => {
    let cancelled = false;
    const currentUrl = window.location.href;
    const dispatcher = new IntentDispatcher(router, openFlowPad);

    void dispatcher.dispatch(currentUrl).finally(() => {
      if (cancelled) return;
      // Ask intents open FlowPad in-place; return to chat home after dispatch.
      if (currentUrl.includes('/intent/ask')) {
        router.replace('/');
      }
    });

    return () => {
      cancelled = true;
    };
  }, [router, openFlowPad]);

  return null;
}
