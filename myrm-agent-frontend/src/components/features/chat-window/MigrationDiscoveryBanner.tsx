'use client';

/**
 * [INPUT]
 * @/services/migrationDiscovery::discoverMigrationSources (POS: External assistant data auto-discovery client)
 * @/hooks/ui/useProactiveDismissal::OFFER_SNOOZE_DAYS, dismissProactive, isProactiveDismissed (POS: per-device memory for closed cards)
 * @/hooks/ui/useNoticeSlot::useNoticeSlot (POS: one first-screen notice at a time)
 *
 * [OUTPUT]
 * MigrationDiscoveryBanner: one-click import prompt for detected external assistant data.
 *
 * [POS]
 * Local/Tauri-only banner shown in EmptyChat when external assistant data is detected.
 * Renders nothing while scanning and when nothing is found, so users without external data never see a
 * placeholder card flash in and out. Routes user to migration wizard in settings for full preview and confirm flow.
 * Closing it snoozes the offer on this device for a week, and the disk scan is skipped while it is snoozed.
 * It waits for the notice slot, so it never appears above or beside another notice that is already readable.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/primitives/button';
import { useNoticeSlot } from '@/hooks/ui/useNoticeSlot';
import { OFFER_SNOOZE_DAYS, dismissProactive, isProactiveDismissed } from '@/hooks/ui/useProactiveDismissal';
import { isLocalMode } from '@/lib/deploy-mode';
import {
  canDeepLinkMigrationSource,
  discoverMigrationSources,
  getMigrationSourceDisplayName,
  type ExternalSource,
} from '@/services/migrationDiscovery';
import { IconArrowRight, IconDownload } from '@/components/features/icons/PremiumIcons';

type BannerState = 'idle' | 'found' | 'dismissed';

const DISMISS_KEY = 'migration-discovery';

export default function MigrationDiscoveryBanner() {
  const t = useTranslations('chat.migrationDiscovery');
  const router = useRouter();
  const [state, setState] = useState<BannerState>('idle');
  const [sources, setSources] = useState<ExternalSource[]>([]);
  const found = state === 'found' && sources.length > 0;
  const holdsSlot = useNoticeSlot('migration-discovery', found);

  useEffect(() => {
    if (!isLocalMode()) {
      return;
    }

    if (isProactiveDismissed(DISMISS_KEY)) {
      return;
    }

    let cancelled = false;
    const scan = async () => {
      try {
        const result = await discoverMigrationSources();
        if (cancelled) {
          return;
        }
        if (result.sources.length > 0) {
          setSources(result.sources);
          setState('found');
        } else {
          setState('idle');
        }
      } catch {
        setState('idle');
      }
    };

    void scan();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleDismiss = useCallback(() => {
    setState('dismissed');
    dismissProactive(DISMISS_KEY, { snoozeDays: OFFER_SNOOZE_DAYS });
  }, []);

  const handleNavigate = useCallback(() => {
    if (sources.length === 1) {
      const sourceId = sources[0].competitor;
      if (!canDeepLinkMigrationSource(sourceId)) {
        router.push('/settings/memory?sub=migration');
        return;
      }
      router.push(`/settings/memory?sub=migration&source=${encodeURIComponent(sourceId)}`);
      return;
    }
    router.push('/settings/memory?sub=migration');
  }, [router, sources]);

  if (!isLocalMode() || !found || !holdsSlot) {
    return null;
  }

  const totalMemories = sources.reduce((sum, s) => sum + s.memory_count_estimate, 0);
  const totalSkills = sources.reduce((sum, s) => sum + s.skill_count, 0);
  const hasApiKeys = sources.some((s) => s.has_api_keys);
  const competitorNames = sources.map((s) => getMigrationSourceDisplayName(s.competitor)).join(', ');

  const description =
    totalSkills > 0
      ? t('description', { memoryCount: totalMemories, skillCount: totalSkills })
      : totalMemories > 0
        ? t('descriptionMemoryOnly', { memoryCount: totalMemories })
        : t('descriptionGeneric');

  return (
    <div className="w-full overflow-visible rounded-xl border border-primary/20 bg-primary/[0.04] p-4 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <IconDownload className="h-4 w-4 text-primary" />
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium">{t('title', { competitor: competitorNames })}</span>
            <span className="text-xs text-muted-foreground">{description}</span>
            {hasApiKeys && <span className="text-xs text-amber-600 dark:text-amber-400">{t('apiKeysHint')}</span>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 overflow-visible py-1 sm:shrink-0">
          <Button className="btn-brand-elevation h-8 shrink-0 px-3 text-sm" onClick={handleNavigate}>
            <IconArrowRight className="mr-1.5 h-3.5 w-3.5" />
            {t('importButton')}
          </Button>
          <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={handleDismiss}>
            {t('dismiss')}
          </Button>
        </div>
      </div>
    </div>
  );
}
