'use client';

import { Wand2, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

export interface Turn1CatalogPreview {
  inline_count: number;
  hidden_count: number;
  search_mounted: boolean;
  inline_cap: number;
}

export interface ActionSpaceAccuracyRadarProps {
  isEvaluating: boolean;
  accuracyLevel: number;
  isNoiseHigh: boolean;
  isNoiseCritical: boolean;
  staleCoreSkillCount: number;
  isSmartPruning?: boolean;
  onSmartPrune: () => void;
  catalogPreview?: Turn1CatalogPreview | null;
  showTurn1Catalog?: boolean;
}

export function ActionSpaceAccuracyRadar({
  isEvaluating,
  accuracyLevel,
  isNoiseHigh,
  isNoiseCritical,
  staleCoreSkillCount,
  isSmartPruning = false,
  onSmartPrune,
  catalogPreview = null,
  showTurn1Catalog = false,
}: ActionSpaceAccuracyRadarProps) {
  const t = useTranslations('agent.configEditor.actionSpaceRadar');

  const statusMessage = isEvaluating
    ? t('evaluatingHint')
    : isNoiseCritical
      ? t('statusCritical')
      : isNoiseHigh
        ? t('statusHigh')
        : t('statusGood');

  return (
    <div className="p-3 rounded-xl bg-muted/30 border border-border/50 space-y-2 mb-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground flex items-center gap-1.5">
          <Wand2 size={14} className="text-blue-500" />
          {t('title')}
        </span>
        <span
          className={cn(
            'font-mono text-xs',
            isEvaluating
              ? 'text-muted-foreground animate-pulse'
              : isNoiseCritical
                ? 'text-red-500 font-bold'
                : isNoiseHigh
                  ? 'text-amber-500 font-bold'
                  : 'text-green-500 font-bold',
          )}
        >
          {isEvaluating ? t('evaluating') : `${accuracyLevel}%`}
        </span>
      </div>
      <div className="h-2 w-full bg-muted rounded-full overflow-hidden flex">
        <div
          className={cn(
            'h-full transition-all duration-500',
            isEvaluating
              ? 'bg-muted-foreground/30 animate-pulse'
              : isNoiseCritical
                ? 'bg-red-500'
                : isNoiseHigh
                  ? 'bg-amber-500'
                  : 'bg-green-500',
          )}
          style={{ width: isEvaluating ? '100%' : `${accuracyLevel}%` }}
        />
      </div>
      <p
        className={cn(
          'text-xs mt-1 font-medium transition-opacity',
          isEvaluating ? 'opacity-50' : 'opacity-100',
          isNoiseCritical ? 'text-red-500' : isNoiseHigh ? 'text-amber-500' : 'text-green-600 dark:text-green-400',
        )}
      >
        {statusMessage}
      </p>

      {showTurn1Catalog && catalogPreview && !isEvaluating && (
        <div className="mt-2 p-2 rounded-lg bg-muted/40 border border-border/60 space-y-1">
          <p className="text-xs font-medium text-foreground">{t('turn1CatalogTitle')}</p>
          <p className="text-xs font-mono text-muted-foreground">
            {t('turn1CatalogSummary', {
              inline: catalogPreview.inline_count,
              hidden: catalogPreview.hidden_count,
              searchState: catalogPreview.search_mounted ? t('turn1CatalogSearchOn') : t('turn1CatalogSearchOff'),
            })}
          </p>
          {catalogPreview.hidden_count > 0 && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t('turn1CatalogOverCapHint', { cap: catalogPreview.inline_cap })}
            </p>
          )}
        </div>
      )}

      {staleCoreSkillCount > 0 && !isEvaluating && (
        <div className="mt-2 p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-start gap-2">
          <span className="text-blue-500 mt-0.5">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
          </span>
          <div className="flex-1">
            <p className="text-xs text-blue-700 dark:text-blue-300 font-medium">
              {t('staleSkillsNotice', { count: staleCoreSkillCount })}
            </p>
            <button
              type="button"
              disabled={isSmartPruning}
              onClick={onSmartPrune}
              className={cn(
                'text-xs font-bold text-blue-600 dark:text-blue-400 mt-1 inline-flex items-center gap-1',
                isSmartPruning ? 'opacity-60 cursor-not-allowed' : 'hover:underline',
              )}
            >
              {isSmartPruning ? <Loader2 size={12} className="animate-spin" /> : null}
              {isSmartPruning ? t('smartPruneRunning') : t('smartPrune')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
