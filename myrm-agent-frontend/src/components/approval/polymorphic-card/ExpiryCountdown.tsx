'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Clock } from 'lucide-react';

function formatRemaining(remainingMs: number, t: ReturnType<typeof useTranslations>): string {
  if (remainingMs <= 0) {
    return t('expired');
  }
  const totalSeconds = Math.ceil(remainingMs / 1000);
  if (totalSeconds < 60) {
    return t('expiresIn', { seconds: totalSeconds });
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export function ExpiryCountdown({ expiresAt }: { expiresAt: string }) {
  const t = useTranslations('toolApproval');
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const expiresAtMs = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresAtMs)) {
    return null;
  }

  const remaining = expiresAtMs - now;
  const isExpired = remaining <= 0;
  const isUrgent = remaining < 60_000;

  return (
    <span
      className={
        'inline-flex items-center gap-1 text-xs ' +
        (isExpired
          ? 'text-destructive-text'
          : isUrgent
            ? 'text-amber-600 dark:text-amber-400'
            : 'text-muted-foreground')
      }
      aria-live="polite"
    >
      <Clock className="h-3 w-3" aria-hidden="true" />
      {formatRemaining(remaining, t)}
    </span>
  );
}
