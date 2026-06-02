'use client';

import { useCallback, useEffect, useRef } from 'react';
import { toast } from '@/lib/utils/toast';
import { apiRequest } from '@/lib/api';
import useAuthStore from '@/store/useAuthStore';

const MAX_SEEN_IDS = 300;

interface PushMessage {
  id: string;
  text: string;
  level: 'success' | 'error' | 'info';
  job_name: string;
}

interface PushResponse {
  messages: PushMessage[];
}

export default function CronPushPoller() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const seenRef = useRef<Set<string>>(new Set());

  const poll = useCallback(async () => {
    if (document.hidden) return;

    try {
      const res = await apiRequest<PushResponse>('/cron/push-messages');
      if (!res?.messages?.length) return;

      const seen = seenRef.current;
      if (seen.size > MAX_SEEN_IDS) seen.clear();

      for (const msg of res.messages) {
        if (seen.has(msg.id)) continue;
        seen.add(msg.id);

        const toastFn = msg.level === 'error' ? toast.error : msg.level === 'success' ? toast.success : toast.info;

        toastFn(msg.text, { duration: 8000 });
      }
    } catch {
      // silently ignore poll failures
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;

    poll();

    let timeoutId: NodeJS.Timeout;
    const handleSseEvent = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => poll(), 1000);
    };
    window.addEventListener('cron_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);

    const onVisibility = () => {
      if (document.visibilityState === 'visible') poll();
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      window.removeEventListener('cron_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
      document.removeEventListener('visibilitychange', onVisibility);
      clearTimeout(timeoutId);
    };
  }, [isAuthenticated, poll]);

  return null;
}
