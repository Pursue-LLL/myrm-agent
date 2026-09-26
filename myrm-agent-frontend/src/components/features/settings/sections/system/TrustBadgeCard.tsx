'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconCheck, IconAlertCircle, IconShield } from '@/components/features/icons/PremiumIcons';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { cn } from '@/lib/utils/classnameUtils';

type SafetyState = 'safe' | 'placeholder_dev' | 'placeholder_prod' | 'invalid' | 'unknown';

const OFFICIAL_SITE_URL = 'https://myrmagent.ai';
const OFFICIAL_DOWNLOAD_URL = 'https://myrmagent.ai/download';
const OFFICIAL_RELEASES_URL = 'https://github.com/Pursue-LLL/myrm-agent/releases';

async function queryUpdaterSafety(): Promise<SafetyState> {
  if (!isTauriRuntime()) {
    return 'unknown';
  }
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    const state = await invoke<string>('get_updater_safety');
    if (state === 'safe' || state === 'placeholder_dev' || state === 'placeholder_prod' || state === 'invalid') {
      return state;
    }
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

const TrustBadgeCard = memo(() => {
  const t = useTranslations('settings.system.trustBadge');
  const [state, setState] = useState<SafetyState>('unknown');

  useEffect(() => {
    let cancelled = false;
    void queryUpdaterSafety().then((s) => {
      if (!cancelled) {
        setState(s);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!isTauriRuntime()) {
    return null;
  }

  const tone =
    state === 'safe'
      ? 'text-emerald-400'
      : state === 'unknown'
        ? 'text-muted-foreground'
        : 'text-destructive';

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconShield className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="space-y-6 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
        <div className="flex items-center gap-2">
          {state === 'safe' && <IconCheck className="w-4 h-4 text-emerald-400" />}
          {state !== 'safe' && state !== 'unknown' && <IconAlertCircle className="w-4 h-4 text-destructive" />}
          <p className={cn('text-sm font-bold text-foreground', tone)}>{t(`state.${state}`)}</p>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">{t(`hint.${state}`)}</p>
        <div className="flex flex-wrap gap-2">
          <a
            href={OFFICIAL_SITE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
          >
            {t('officialSite')}
          </a>
          <a
            href={OFFICIAL_DOWNLOAD_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
          >
            {t('officialDownload')}
          </a>
          <a
            href={OFFICIAL_RELEASES_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
          >
            {t('officialReleases')}
          </a>
        </div>
      </div>
    </section>
  );
});

TrustBadgeCard.displayName = 'TrustBadgeCard';
export default TrustBadgeCard;
