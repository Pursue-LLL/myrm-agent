'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/useToast';
import {
  getPreferences,
  pinPreference,
  forgetPreference,
  unpinPreference,
  unforgetPreference,
  type PreferenceFacet,
  type PreferenceFacetListResponse,
} from '@/services/memoryPreferences';
import { DashboardBrowsingIcon, PinIcon, Delete02Icon, UndoIcon } from 'hugeicons-react';

const LIFECYCLE_CONFIG: Record<string, { color: string; dotColor: string }> = {
  active: { color: 'text-emerald-600 dark:text-emerald-400', dotColor: 'bg-emerald-500' },
  provisional: { color: 'text-amber-600 dark:text-amber-400', dotColor: 'bg-amber-500' },
  candidate: { color: 'text-blue-600 dark:text-blue-400', dotColor: 'bg-blue-500' },
  dropped: { color: 'text-zinc-400 dark:text-zinc-500', dotColor: 'bg-zinc-400' },
};

const CATEGORY_COLORS: Record<string, string> = {
  identity: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
  veto: 'bg-red-500/10 text-red-600 dark:text-red-400',
  tooling: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400',
  goal: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  style: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  channel: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
};

const PreferenceStabilityCard = memo<{ className?: string }>(({ className }) => {
  const t = useTranslations('memory.preferenceStability');
  const [data, setData] = useState<PreferenceFacetListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForgotten, setShowForgotten] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await getPreferences();
      setData(res);
    } catch {
      // silently ignore if API not available
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handlePin = useCallback(
    async (facetId: string) => {
      try {
        await pinPreference(facetId);
        toast({ title: t('pinSuccess') });
        fetchData();
      } catch {
        toast({ title: t('operationFailed'), variant: 'destructive' });
      }
    },
    [t, fetchData],
  );

  const handleUnpin = useCallback(
    async (facetId: string) => {
      try {
        await unpinPreference(facetId);
        toast({ title: t('unpinSuccess') });
        fetchData();
      } catch {
        toast({ title: t('operationFailed'), variant: 'destructive' });
      }
    },
    [t, fetchData],
  );

  const handleForget = useCallback(
    async (facetId: string) => {
      try {
        await forgetPreference(facetId);
        toast({ title: t('forgetSuccess') });
        fetchData();
      } catch {
        toast({ title: t('operationFailed'), variant: 'destructive' });
      }
    },
    [t, fetchData],
  );

  const handleUnforget = useCallback(
    async (facetId: string) => {
      try {
        await unforgetPreference(facetId);
        toast({ title: t('unforgetSuccess') });
        fetchData();
      } catch {
        toast({ title: t('operationFailed'), variant: 'destructive' });
      }
    },
    [t, fetchData],
  );

  if (loading || !data || data.total === 0) return null;

  const activeItems = data.items.filter((f) => f.lifecycle !== 'dropped' && !f.user_forgotten);
  const forgottenItems = data.items.filter((f) => f.user_forgotten);
  if (activeItems.length === 0 && forgottenItems.length === 0) return null;

  return (
    <div className={cn('rounded-xl border border-border/50 bg-card p-4', className)}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <DashboardBrowsingIcon size={14} className="text-primary" />
          {t('title')}
        </h3>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            {data.active_count}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            {data.provisional_count}
          </span>
        </div>
      </div>

      <div className="space-y-1.5">
        {activeItems.slice(0, 12).map((facet) => (
          <FacetRow
            key={facet.id}
            facet={facet}
            t={t}
            onPin={handlePin}
            onUnpin={handleUnpin}
            onForget={handleForget}
            onUnforget={handleUnforget}
          />
        ))}
      </div>

      {forgottenItems.length > 0 && (
        <div className="mt-3 border-t border-border/30 pt-2">
          <button
            onClick={() => setShowForgotten(!showForgotten)}
            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          >
            {t('forgotten')} ({forgottenItems.length})
          </button>
          {showForgotten && (
            <div className="mt-1.5 space-y-1.5">
              {forgottenItems.map((facet) => (
                <FacetRow
                  key={facet.id}
                  facet={facet}
                  t={t}
                  onPin={handlePin}
                  onUnpin={handleUnpin}
                  onForget={handleForget}
                  onUnforget={handleUnforget}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

PreferenceStabilityCard.displayName = 'PreferenceStabilityCard';

const FacetRow = memo<{
  facet: PreferenceFacet;
  t: ReturnType<typeof useTranslations>;
  onPin: (id: string) => void;
  onUnpin: (id: string) => void;
  onForget: (id: string) => void;
  onUnforget: (id: string) => void;
}>(({ facet, t, onPin, onUnpin, onForget, onUnforget }) => {
  const lifecycle = LIFECYCLE_CONFIG[facet.lifecycle] ?? LIFECYCLE_CONFIG.candidate;
  const categoryColor = CATEGORY_COLORS[facet.category] ?? CATEGORY_COLORS.style;
  const categoryLabel = t(`category.${facet.category}` as Parameters<typeof t>[0]);

  return (
    <div
      className={cn(
        'flex items-center gap-2 group py-1 px-1.5 rounded-full hover:bg-accent/50 transition-colors',
        facet.user_forgotten && 'opacity-50',
      )}
    >
      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', lifecycle.dotColor)} />

      <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full shrink-0', categoryColor)}>{categoryLabel}</span>

      <span
        className={cn(
          'text-xs truncate flex-1 min-w-0',
          facet.user_forgotten ? 'text-muted-foreground line-through' : 'text-foreground',
        )}
      >
        {facet.value}
      </span>

      <span className="text-[10px] text-muted-foreground shrink-0 tabular-nums">{facet.evidence_count}x</span>

      {facet.user_forgotten ? (
        <button
          onClick={() => onUnforget(facet.id)}
          className="p-0.5 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
          title={t('unforget')}
        >
          <UndoIcon size={11} />
        </button>
      ) : facet.user_pinned ? (
        <button
          onClick={() => onUnpin(facet.id)}
          className="p-0.5 rounded text-primary hover:bg-primary/10 transition-colors"
          title={t('unpin')}
        >
          <PinIcon size={12} />
        </button>
      ) : (
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onPin(facet.id)}
            className="p-0.5 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
            title={t('pin')}
          >
            <PinIcon size={11} />
          </button>
          <button
            onClick={() => onForget(facet.id)}
            className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            title={t('forget')}
          >
            <Delete02Icon size={11} />
          </button>
        </div>
      )}
    </div>
  );
});

FacetRow.displayName = 'FacetRow';

export default PreferenceStabilityCard;
