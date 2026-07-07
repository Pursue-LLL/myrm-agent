'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { getCachedBlueprints, humanizeSchedule, invalidateBlueprintCache, loadBlueprints, type CronBlueprint } from './cron-blueprints';

interface BlueprintCatalogProps {
  onSelect: (blueprint: CronBlueprint) => void;
  maxItems?: number;
}

export default function BlueprintCatalog({ onSelect, maxItems }: BlueprintCatalogProps) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const [blueprints, setBlueprints] = useState<readonly CronBlueprint[]>(getCachedBlueprints());
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(blueprints.length === 0);

  const fetchCatalog = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    return loadBlueprints()
      .then((items) => {
        setBlueprints(items);
        setLoadError(false);
      })
      .catch(() => {
        setBlueprints([]);
        setLoadError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void fetchCatalog();
  }, [fetchCatalog]);

  const handleRetry = () => {
    invalidateBlueprintCache();
    void fetchCatalog();
  };

  if (loadError) {
    return (
      <div className="rounded-lg border border-dashed border-border/70 bg-muted/20 px-4 py-6 text-center space-y-3">
        <p className="text-sm text-muted-foreground">{t('blueprint.loadError')}</p>
        <Button type="button" variant="outline" size="sm" onClick={handleRetry}>
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
          {t('blueprint.loadRetry')}
        </Button>
      </div>
    );
  }

  if (loading && blueprints.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-6">{t('blueprint.loading')}</p>
    );
  }

  const items = maxItems ? blueprints.slice(0, maxItems) : blueprints;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {items.map((bp) => {
        const defaultSchedule = bp.buildSchedule(
          Object.fromEntries(bp.slots.map((s) => [s.name, s.default])),
        );
        const scheduleText = humanizeSchedule(defaultSchedule);

        return (
          <button
            key={bp.id}
            type="button"
            onClick={() => onSelect(bp)}
            className="group flex items-start gap-3 rounded-lg border border-border bg-card p-3 text-left transition-all hover:border-primary/40 hover:bg-primary/5 hover:shadow-sm"
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <bp.icon className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground group-hover:text-primary truncate">
                {bp.title?.[locale] || t(bp.titleKey)}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                {bp.description?.[locale] || t(bp.descKey)}
              </p>
              <p className="text-[11px] text-muted-foreground/70 mt-1">
                {scheduleText}
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}
