'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { parseIntentUrl } from '@/lib/intent-dispatcher/schema';
import { useFlowPadStore } from '@/store/useFlowPadStore';

/**
 * Web/SaaS deep-link landing page.
 * Handles /intent/* URLs that are not part of normal app routes.
 */
export default function IntentPage() {
  const router = useRouter();
  const openFlowPad = useFlowPadStore((state) => state.open);
  const hasDispatchedRef = useRef(false);

  useEffect(() => {
    if (hasDispatchedRef.current) {
      return;
    }
    hasDispatchedRef.current = true;

    let cancelled = false;
    const currentUrl = window.location.href;
    const dispatcher = new IntentDispatcher(router, openFlowPad);
    let shouldReturnHome = false;

    try {
      const parsed = parseIntentUrl(currentUrl);
      shouldReturnHome = parsed.action === 'ask';
    } catch {
      // Invalid intent route should not leave user on a blank /intent page.
      router.replace('/');
      return () => {
        cancelled = true;
      };
    }

    void dispatcher.dispatch(currentUrl).finally(() => {
      if (cancelled) return;
      if (shouldReturnHome) {
        router.replace('/');
      }
    });

    return () => {
      cancelled = true;
    };
  }, [router, openFlowPad]);

  return null;
}
