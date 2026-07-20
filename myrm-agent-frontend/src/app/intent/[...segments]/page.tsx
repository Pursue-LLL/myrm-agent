'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { parseIntentUrl } from '@/lib/intent-dispatcher/schema';
import { useFlowPadStore } from '@/store/useFlowPadStore';

/**
 * [INPUT]
 * @/lib/intent-dispatcher::IntentDispatcher (POS: UIP dispatcher for route/open actions)
 * @/lib/intent-dispatcher/schema::parseIntentUrl (POS: UIP URL parser and whitelist validator)
 * @/store/useFlowPadStore::useFlowPadStore (POS: FlowPad modal state store)
 *
 * [OUTPUT]
 * IntentPage: Dispatch /intent/* URLs exactly once and route back to home for ask intents.
 *
 * [POS]
 * Web/SaaS intent landing page. It consumes deep-link style routes in browser runtime and forwards them to the UIP dispatcher.
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
