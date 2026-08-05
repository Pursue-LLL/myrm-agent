'use client';

/**
 * [INPUT]
 * @/services/memory-health::getSharedContextMemoryHealth (POS: memory embedding health API)
 *
 * [OUTPUT]
 * MemoryRecallDegradedBanner: Chat/Memory top-bar banner when semantic recall is degraded.
 *
 * [POS]
 * Vector recall degraded mode UX (#3). Reuses health probe — shows only when not ready.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Loader2, RefreshCw, ShieldAlert, X } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { getSharedContextMemoryHealth, type SharedContextMemoryHealthResponse } from '@/services/memory-health';

interface MemoryRecallDegradedBannerProps {
  compact?: boolean;
  dismissStorageKey?: string;
  className?: string;
}

export const MemoryRecallDegradedBanner = memo(function MemoryRecallDegradedBanner({
  compact = false,
  dismissStorageKey,
  className,
}: MemoryRecallDegradedBannerProps) {
  const t = useTranslations('memoryRecallDegraded');
  const tMemory = useTranslations('memory');
  const [health, setHealth] = useState<SharedContextMemoryHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');
  const [dismissed, setDismissed] = useState(false);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    setErrorMessage('');
    try {
      const next = await getSharedContextMemoryHealth(false);
      setHealth(next);
    } catch (error) {
      setHealth(null);
      setErrorMessage(error instanceof Error ? error.message : tMemory('unknownError'));
    } finally {
      setLoading(false);
    }
  }, [tMemory]);

  useEffect(() => {
    if (dismissStorageKey && typeof window !== 'undefined') {
      setDismissed(window.sessionStorage.getItem(dismissStorageKey) === '1');
    }
    void loadHealth();
  }, [dismissStorageKey, loadHealth]);

  const handleDismiss = () => {
    setDismissed(true);
    if (dismissStorageKey && typeof window !== 'undefined') {
      window.sessionStorage.setItem(dismissStorageKey, '1');
    }
  };

  if (dismissed) {
    return null;
  }

  if (loading && health === null && !errorMessage) {
    return null;
  }

  if (errorMessage && health === null) {
    return (
      <div
        role="alert"
        data-testid="memory-recall-degraded-banner"
        className={cn(
          'rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive',
          compact && 'rounded-lg py-2 text-xs',
          className,
        )}
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-2 min-w-0">
            <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="font-medium">{t('unavailable')}</p>
              {!compact && <p className="mt-0.5 text-xs opacity-90 leading-relaxed">{errorMessage}</p>}
            </div>
          </div>
          <button
            type="button"
            onClick={() => void loadHealth()}
            className="inline-flex items-center gap-1 rounded-md border border-current/25 px-2 py-1 text-[11px] font-medium hover:bg-background/40"
          >
            <RefreshCw className="h-3 w-3" />
            {t('retry')}
          </button>
        </div>
      </div>
    );
  }

  if (health === null || health.ready) {
    return null;
  }

  return (
    <div
      role="alert"
      data-testid="memory-recall-degraded-banner"
      className={cn(
        'rounded-xl border border-amber-500/35 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-900 dark:text-amber-200',
        compact && 'rounded-lg py-2 text-xs',
        className,
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-2 min-w-0">
          {loading ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin mt-0.5" />
          ) : (
            <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
          )}
          <div className="min-w-0">
            <p className="font-medium">{t('title')}</p>
            {!compact && <p className="mt-0.5 text-xs opacity-90 leading-relaxed">{t('description')}</p>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Link
            href="/settings/memory?sub=explorer"
            className="rounded-md border border-current/25 px-2 py-1 text-[11px] font-medium hover:bg-background/40"
          >
            {t('actionDoctor')}
          </Link>
          {dismissStorageKey && (
            <button
              type="button"
              onClick={handleDismiss}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
              {t('dismiss')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
