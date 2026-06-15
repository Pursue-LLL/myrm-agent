'use client';

/**
 * [INPUT]
 * @/services/migrationDiscovery::discoverMigrationSources (POS: External assistant data auto-discovery client)
 *
 * [OUTPUT]
 * MigrationDiscoveryBanner: one-click import prompt for detected competitor AI assistant data.
 *
 * [POS]
 * Local/Tauri-only banner shown in EmptyChat when external assistant data is detected.
 * Routes user to migration wizard in settings for full preview and confirm flow.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/primitives/button';
import { isLocalMode } from '@/lib/deploy-mode';
import { discoverMigrationSources, getMigrationSourceDisplayName, type ExternalSource } from '@/services/migrationDiscovery';
import { IconArrowRight, IconDownload, IconLoader } from '@/components/features/icons/PremiumIcons';

type BannerState = 'idle' | 'scanning' | 'found' | 'dismissed';

export default function MigrationDiscoveryBanner() {
  const t = useTranslations('chat.migrationDiscovery');
  const router = useRouter();
  const [state, setState] = useState<BannerState>('idle');
  const [sources, setSources] = useState<ExternalSource[]>([]);

  useEffect(() => {
    if (!isLocalMode()) return;

    const dismissed =
      sessionStorage.getItem('migration_discovery_dismissed') ??
      sessionStorage.getItem('competitor_migration_dismissed');
    if (dismissed === 'true') {
      setState('dismissed');
      return;
    }

    let cancelled = false;
    const scan = async () => {
      setState('scanning');
      try {
        const result = await discoverMigrationSources();
        if (cancelled) return;
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
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
  }, []);

  const handleNavigate = useCallback(() => {
    router.push('/settings/memory?sub=migration');
  }, [router]);

  if (!isLocalMode() || state === 'idle' || state === 'dismissed') return null;

  if (state === 'scanning') {
    return (
      <div className="w-full rounded-xl border border-border/60 bg-secondary/30 p-4">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <IconLoader className="h-4 w-4 animate-spin" />
          <span>{t('detecting')}</span>
        </div>
      </div>
    );
  }

  const primarySource = sources[0];
  if (!primarySource) return null;

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
    <div className="w-full rounded-xl border border-primary/20 bg-primary/[0.04] p-4 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-500">
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
        <div className="flex items-center gap-2 sm:shrink-0">
          <Button size="sm" className="h-8 text-xs" onClick={handleNavigate}>
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
