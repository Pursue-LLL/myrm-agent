'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Skeleton } from '@/components/primitives/skeleton';
import { apiRequest } from '@/lib/api';
import { cn } from '@/lib/utils/classnameUtils';
import { CatalogConnectionStatus } from '@/components/features/settings/sections/integration/integrations/CatalogConnectionStatus';
import { IntegrationConnectDialog } from '@/components/features/settings/sections/integration/integrations/IntegrationConnectDialog';
import { useCatalogConnectionState } from '@/components/features/settings/sections/integration/integrations/catalog-connection';
import { useCatalogLocale } from '@/components/features/settings/sections/integration/integrations/catalog-locale';
import { SERVICE_ICONS } from '@/components/features/settings/sections/integration/integrations/service-icons';
import type {
  CatalogEntry,
  CatalogResponse,
} from '@/components/features/settings/sections/integration/integrations/catalog-types';

const FEATURED_SERVICE_IDS = ['github', 'notion', 'microsoft-todo', 'slack', 'linear'] as const;

interface ToolsConnectOnboardingStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

export default function ToolsConnectOnboardingStep({ onComplete, onSkip }: ToolsConnectOnboardingStepProps) {
  const t = useTranslations('boot.onboarding.toolsConnect');
  const locale = useCatalogLocale();
  const resolveConnectionState = useCatalogConnectionState();
  const [entries, setEntries] = useState<CatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectEntry, setConnectEntry] = useState<CatalogEntry | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const data = await apiRequest<CatalogResponse>('/integrations/catalog', { silent: true });
        if (!mounted) {
          return;
        }
        const featured = FEATURED_SERVICE_IDS.map((id) => data.entries.find((e) => e.id === id)).filter(
          (e): e is CatalogEntry => e !== null && e !== undefined,
        );
        const resolved = featured.length > 0 ? featured : data.entries.slice(0, 5);
        if (resolved.length === 0) {
          onSkip();
          return;
        }
        setEntries(resolved);
      } catch {
        if (mounted) {
          onSkip();
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (entries.length === 0) {
    return null;
  }

  const hasConnectedEntry = entries.some((entry) => resolveConnectionState(entry) === 'connected');

  return (
    <div className="space-y-6">
      <div className="grid gap-3">
        {entries.map((entry) => {
          const IconComponent = SERVICE_ICONS[entry.icon];
          const connectionState = resolveConnectionState(entry);
          const name = locale === 'zh' && entry.nameZh ? entry.nameZh : entry.name;
          const descText = locale === 'zh' ? entry.descriptionZh : entry.description;

          return (
            <button
              key={entry.id}
              type="button"
              className={cn(
                'flex items-center gap-4 p-4 rounded-xl border bg-card transition-colors text-left w-full',
                connectionState === 'available' && 'hover:bg-accent/50',
              )}
              onClick={() => setConnectEntry(entry)}
              disabled={connectionState !== 'available'}
            >
              <div className="rounded-lg bg-muted p-2.5 shrink-0">
                {IconComponent ? (
                  <IconComponent className="h-6 w-6 text-foreground" />
                ) : (
                  <div className="h-6 w-6 rounded bg-muted-foreground/20" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-foreground">{name}</div>
                {descText && <div className="text-xs text-muted-foreground mt-0.5 truncate">{descText}</div>}
              </div>
              <div className="shrink-0">
                {connectionState === 'available' ? (
                  <span className="text-xs font-medium text-primary">{t('connectButton')}</span>
                ) : (
                  <CatalogConnectionStatus state={connectionState} />
                )}
              </div>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground text-center">{t('moreHint')}</p>

      <div className="flex flex-col items-center gap-3 pt-2">
        {hasConnectedEntry && (
          <Button size="lg" className="w-full sm:w-auto min-w-[220px]" onClick={onComplete}>
            {t('continueButton')}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onSkip}>
          {t('skipButton')}
        </Button>
      </div>

      {connectEntry && (
        <IntegrationConnectDialog
          entry={connectEntry}
          locale={locale}
          onClose={() => setConnectEntry(null)}
          onConnected={() => setConnectEntry(null)}
        />
      )}
    </div>
  );
}
