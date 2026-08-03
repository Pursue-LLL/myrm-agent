'use client';

import { useCallback, useEffect, useState } from 'react';
import { fetchRunDigest, type RunDigest } from '@/services/copilot';

export function useRunDigest(chatId: string | null) {
  const [digest, setDigest] = useState<RunDigest | null>(null);

  const refresh = useCallback(async () => {
    if (!chatId) {
      setDigest(null);
      return;
    }
    const next = await fetchRunDigest(chatId);
    setDigest(next);
  }, [chatId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ chat_id?: string; digest?: RunDigest }>).detail;
      if (!chatId || detail?.chat_id !== chatId) return;
      if (detail.digest) {
        setDigest(detail.digest);
      } else {
        void refresh();
      }
    };
    window.addEventListener('run-digest-updated', handler);
    return () => window.removeEventListener('run-digest-updated', handler);
  }, [chatId, refresh]);

  useEffect(() => {
    const handler = () => {
      if (!chatId) return;
      void refresh();
    };
    window.addEventListener('app_resync_required', handler);
    return () => window.removeEventListener('app_resync_required', handler);
  }, [chatId, refresh]);

  return { digest, refresh };
}
