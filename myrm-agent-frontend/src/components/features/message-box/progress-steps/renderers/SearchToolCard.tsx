import React, { useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { FolderSearch, RefreshCw, SearchCode, Zap } from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import type { SearchToolItem } from '../utils';

interface SearchToolCardProps {
  items: SearchToolItem[];
  toolName?: string | null;
  messageId: string;
  stepIndex: number;
  onForceRefresh?: (item: SearchToolItem) => void;
}

function formatCacheAge(
  seconds: number | undefined,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  if (seconds === undefined || seconds <= 5) {
    return t('justNow');
  }
  if (seconds < 60) {
    return t('secondsAgo', { count: seconds });
  }
  if (seconds < 3600) {
    return t('minutesAgo', { count: Math.floor(seconds / 60) });
  }
  return t('hoursAgo', { count: Math.floor(seconds / 3600) });
}

const SearchToolCard: React.FC<SearchToolCardProps> = ({
  items,
  toolName,
  messageId,
  stepIndex,
  onForceRefresh,
}) => {
  const t = useTranslations('progressSteps.searchTool');
  const isGlob = toolName === 'glob_tool';
  const [refreshingIndices, setRefreshingIndices] = useState<Record<number, boolean>>({});

  const handleForceRefresh = (item: SearchToolItem, index: number) => {
    if (refreshingIndices[index]) {
      return;
    }
    setRefreshingIndices((prev) => ({ ...prev, [index]: true }));

    if (onForceRefresh) {
      onForceRefresh(item);
    } else {
      // Dispatch force-refresh turn instruction via chat store
      const queryText = item.pattern || item.search_path || 'search';
      useChatStore.getState().sendMessage(`[force_refresh] ${queryText}`);
    }

    setTimeout(() => {
      setRefreshingIndices((prev) => ({ ...prev, [index]: false }));
    }, 2000);
  };

  const getScenarioBadge = (scenario?: 'realtime' | 'standard' | 'archive') => {
    switch (scenario) {
      case 'realtime':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            {t('scenarioRealtime')} (3m)
          </span>
        );
      case 'archive':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
            {t('scenarioArchive')} (24h)
          </span>
        );
      case 'standard':
      default:
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground border border-border/40">
            {t('scenarioStandard')} (30m)
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {items.map((item, itemIndex) => {
        const isRefreshing = !!refreshingIndices[itemIndex];
        return (
          <div
            key={`${messageId}-search-${stepIndex}-${itemIndex}`}
            className={cn(
              'rounded-lg border border-border/60 bg-muted/30 px-3 py-2',
              'text-xs sm:text-sm space-y-2',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-muted-foreground">
                {isGlob ? (
                  <FolderSearch className="w-3.5 h-3.5 shrink-0" />
                ) : (
                  <SearchCode className="w-3.5 h-3.5 shrink-0" />
                )}
                <span className="font-medium text-foreground/80">{isGlob ? t('globLabel') : t('grepLabel')}</span>
              </div>

              {item.scenario && getScenarioBadge(item.scenario)}
            </div>

            <div className="font-mono text-[11px] sm:text-xs break-all text-foreground bg-background/60 rounded-md px-2 py-1.5 border border-border/40">
              {item.pattern}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] sm:text-[11px] text-muted-foreground">
              <div className="flex flex-wrap gap-2">
                <span>
                  {t('path')}: <span className="font-mono text-foreground/70">{item.search_path || '.'}</span>
                </span>
                {item.file_pattern && (
                  <span>
                    {t('filePattern')}: <span className="font-mono text-foreground/70">{item.file_pattern}</span>
                  </span>
                )}
              </div>
            </div>

            {/* Cache transparency badge and force-refresh trigger */}
            {item.cached && (
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-border/30 text-[11px]">
                <div className="inline-flex items-center gap-1.5 text-amber-600 dark:text-amber-400 font-medium">
                  <Zap className="w-3.5 h-3.5 shrink-0 animate-pulse text-amber-500" />
                  <span>
                    {t('cacheHitTitle')} ({formatCacheAge(item.cache_age_seconds, t)}
                    {item.saved_tokens !== undefined && `, ${t('savedTokens', { count: item.saved_tokens.toLocaleString() })}`})
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => handleForceRefresh(item, itemIndex)}
                  disabled={isRefreshing}
                  className={cn(
                    'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px]',
                    'text-muted-foreground hover:text-foreground bg-background/80 hover:bg-muted border border-border/50',
                    'transition-colors duration-150 focus:outline-none focus:ring-1 focus:ring-ring',
                    isRefreshing && 'opacity-70 cursor-not-allowed',
                  )}
                  title={t('forceRefresh')}
                >
                  <RefreshCw className={cn('w-3 h-3', isRefreshing && 'animate-spin text-primary')} />
                  <span>{isRefreshing ? t('forceRefreshing') : t('forceRefresh')}</span>
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default SearchToolCard;
