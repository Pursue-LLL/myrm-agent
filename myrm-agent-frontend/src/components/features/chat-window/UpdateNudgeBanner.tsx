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
 * is deferred, quiet hours are active, or the session dismissed it. Security
 * patches bypass deferral and quiet hours.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/primitives/button';
import { getDeferredVersion, getQuietHours, isQuietNow } from '@/lib/update-prefs';
import { IconArrowRight, IconDownload, IconShield } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

const DISMISS_KEY = 'update_nudge_dismissed';

export default function UpdateNudgeBanner() {
  const t = useTranslations('chat.updateNudge');
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [version, setVersion] = useState<string | null>(null);
  const [isSecurity, setIsSecurity] = useState(false);

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
          changelog?: { is_security?: boolean } | null;
        };
        if (cancelled) {
          return;
        }
        const latestVersion = payload.latest?.version ?? null;
        if (payload.stale !== true || !latestVersion) {
          return;
        }
        const isSecurityPatch = payload.changelog?.is_security === true;
        if (!isSecurityPatch && (getDeferredVersion() === latestVersion || isQuietNow(getQuietHours()))) {
          return;
        }
        setIsSecurity(isSecurityPatch);
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
    <div
      className={cn(
        'flex items-center gap-3 rounded-2xl p-4 transition-colors',
        isSecurity
          ? 'border border-amber-500/30 bg-amber-500/5 text-amber-400'
          : 'border border-primary/25 bg-primary/5',
      )}
    >
      {isSecurity ? (
        <IconShield className="w-5 h-5 shrink-0 text-amber-400" />
      ) : (
        <IconDownload className="w-5 h-5 shrink-0 text-primary" />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-foreground">
          {isSecurity ? t('securityTitle', { version: version ?? '' }) : t('title', { version: version ?? '' })}
        </p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {isSecurity ? t('securityDescription') : t('description')}
        </p>
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
