'use client';

/**
 * [INPUT]
 * - /api/v1/health/update-status (POS: stack update truth)
 * - lib/update-prefs (POS: deferral + quiet-hours preferences)
 *
 * [OUTPUT]
 * UpdateNudgeBanner: behind-notice entry to the Stack Update Panel.
 *
 * [POS]
 * EmptyChat banner shown when the server stack is stale, unless the version
 * is deferred, quiet hours are active, or the session dismissed it.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/primitives/button';
import { getDeferredVersion, getQuietHours, isQuietNow } from '@/lib/update-prefs';
import { IconArrowRight, IconDownload } from '@/components/features/icons/PremiumIcons';

const DISMISS_KEY = 'update_nudge_dismissed';

export default function UpdateNudgeBanner() {
  const t = useTranslations('chat.updateNudge');
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (typeof window !== 'undefined' && sessionStorage.getItem(DISMISS_KEY) === 'true') {
      return;
    }
    const probe = async () => {
      try {
        const response = await fetch('/api/v1/health/update-status');
        if (!response.ok || cancelled) {
          return;
        }
        const payload = (await response.json()) as {
          stale?: boolean | null;
          latest?: { version?: string } | null;
        };
        if (cancelled) {
          return;
        }
        const latestVersion = payload.latest?.version ?? null;
        if (payload.stale !== true || !latestVersion) {
          return;
        }
        if (getDeferredVersion() === latestVersion || isQuietNow(getQuietHours())) {
          return;
        }
        setVersion(latestVersion);
        setVisible(true);
      } catch {
        // Update service unreachable — stay silent, never block chat.
      }
    };
    void probe();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleOpen = useCallback(() => {
    router.push('/settings/system?sub=about');
  }, [router]);

  const handleDismiss = useCallback(() => {
    try {
      sessionStorage.setItem(DISMISS_KEY, 'true');
    } catch {
      // Best effort only.
    }
    setVisible(false);
  }, []);

  if (!visible) {
    return null;
  }

  return (
    <div className="flex items-center gap-3 rounded-2xl border border-primary/25 bg-primary/5 p-4">
      <IconDownload className="w-5 h-5 shrink-0 text-primary" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-foreground">{t('title', { version: version ?? '' })}</p>
        <p className="text-xs text-muted-foreground leading-relaxed">{t('description')}</p>
      </div>
      <Button size="sm" onClick={handleOpen} className="gap-1 shrink-0">
        {t('open')}
        <IconArrowRight className="w-3.5 h-3.5" />
      </Button>
      <button
        type="button"
        onClick={handleDismiss}
        aria-label={t('dismiss')}
        className="shrink-0 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {t('dismiss')}
      </button>
    </div>
  );
}
