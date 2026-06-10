'use client';

import { useCallback, useEffect, useState } from 'react';
import { OctagonPause } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';
import { showI18nToast } from '@/services/i18nToastService';

type EStopStatus = {
  level: string;
  reason: string;
};

const ESTOP_CHANGED_EVENT = 'estop-changed';

export default function EStopBanner() {
  const t = useTranslations('estopBanner');
  const [status, setStatus] = useState<EStopStatus | null>(null);
  const [resuming, setResuming] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiRequest<EStopStatus>('/security/estop');
      if (data.level === 'none') {
        setStatus(null);
      } else {
        setStatus(data);
      }
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();

    const onChange = () => {
      void fetchStatus();
    };
    const onFocus = () => {
      void fetchStatus();
    };

    window.addEventListener(ESTOP_CHANGED_EVENT, onChange);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener(ESTOP_CHANGED_EVENT, onChange);
      window.removeEventListener('focus', onFocus);
    };
  }, [fetchStatus]);

  const handleResume = useCallback(async () => {
    setResuming(true);
    try {
      await apiRequest<EStopStatus>('/security/estop', {
        method: 'POST',
        body: JSON.stringify({ action: 'resume' }),
      });
      setStatus(null);
      window.dispatchEvent(new Event(ESTOP_CHANGED_EVENT));
      showI18nToast('commands.builtin.freezeResumed', undefined, { type: 'success' });
    } catch {
      showI18nToast('commands.builtin.freezeFailed', undefined, { type: 'error' });
    } finally {
      setResuming(false);
    }
  }, []);

  if (!status) return null;

  const reasonText = status.reason.trim();

  return (
    <div className="flex items-center justify-between gap-2 px-4 py-1.5 bg-rose-500/10 border-b border-rose-500/20 text-rose-700 dark:text-rose-400">
      <div className="flex items-center gap-2 min-w-0">
        <OctagonPause className="h-3.5 w-3.5 shrink-0" />
        <span className="text-xs font-medium truncate">
          {t('message')}
          {reasonText ? ` — ${reasonText}` : ''}
        </span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs text-rose-700 hover:text-rose-900 hover:bg-rose-500/20 dark:text-rose-400 dark:hover:text-rose-200 dark:hover:bg-rose-500/20 shrink-0"
        onClick={() => void handleResume()}
        disabled={resuming}
      >
        {t('resume')}
      </Button>
    </div>
  );
}
