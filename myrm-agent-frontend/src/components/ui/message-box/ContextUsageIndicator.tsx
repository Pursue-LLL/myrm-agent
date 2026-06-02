'use client';

/**
 * [INPUT]
 * - store/useChatStore::messages, chatId, setActiveSessionAnalyticsId (POS: Chat state management store.)
 * - store/useConfigStore::showContextUsage (POS: User configuration store.)
 * - services/statistics::getSessionAnalytics (POS: Statistics API client DTO layer.)
 * - services/contextHealth::ContextHealth, HealthStatus (POS: Statistics context-health DTO layer.)
 *
 * [OUTPUT]
 * - ContextUsageIndicator: token usage ring with strategy health dot and expandable mini panel.
 *
 * [POS]
 * Context usage and memory strategy indicator for the chat window.
 * Displays token usage ring, strategy health status dot, and on-click mini panel with compaction/pruning/cache details.
 */

import { useMemo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { getSessionAnalytics } from '@/services/statistics';
import type { ContextHealth, HealthStatus } from '@/services/contextHealth';

const STATUS_DOT_COLORS: Record<HealthStatus, string> = {
  inactive: 'bg-muted-foreground/40',
  healthy: 'bg-emerald-500',
  warning: 'bg-amber-500',
  critical: 'bg-rose-500',
};

function formatTokens(tokens: number): string {
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`;
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
  return tokens.toString();
}

function getTextColorByUsage(percentage: number): string {
  if (percentage >= 90) return 'text-red-500';
  if (percentage >= 75) return 'text-amber-500';
  return 'text-primary-dark';
}

type BudgetHealthStatus = 'healthy' | 'warning' | 'critical';

function budgetStatusToHealth(status: BudgetHealthStatus | undefined): HealthStatus {
  if (!status) return 'inactive';
  return status;
}

function resolveDisplayStatus(health: ContextHealth | null): HealthStatus {
  if (!health) return 'inactive';
  if (health.status !== 'inactive') return health.status;
  const { compaction, pruning } = health;
  if ((compaction.active && compaction.count > 0) || (pruning.active && pruning.archived > 0)) {
    return 'healthy';
  }
  return 'inactive';
}

interface MiniPanelContentProps {
  health: ContextHealth | null;
  loading: boolean;
  onNavigateDetails: () => void;
}

function MiniPanelContent({ health, loading, onNavigateDetails }: MiniPanelContentProps) {
  const t = useTranslations('chat.contextUsage.strategy');

  if (loading) {
    return (
      <div className="flex flex-col gap-2 p-3 min-w-[220px] animate-pulse">
        <div className="h-4 bg-muted rounded w-24" />
        <div className="h-3 bg-muted rounded w-full" />
        <div className="h-3 bg-muted rounded w-3/4" />
      </div>
    );
  }

  if (!health) {
    return <div className="p-3 text-xs text-muted-foreground">{t('noData')}</div>;
  }

  const { compaction, pruning, cache } = health;

  return (
    <div className="flex flex-col gap-2.5 p-3 min-w-[220px]">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">{t('title')}</span>
        <span
          className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
            health.status === 'critical'
              ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
              : health.status === 'warning'
                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                : health.status === 'healthy'
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'bg-muted text-muted-foreground'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT_COLORS[health.status]}`} />
          {t(`status.${health.status}`)}
        </span>
      </div>

      <div className="flex flex-col gap-1.5 text-[11px]">
        {compaction.active && (
          <div className="flex items-center justify-between text-muted-foreground">
            <span>{t('compaction')}</span>
            <span className="tabular-nums text-foreground">
              {compaction.count > 0
                ? t('compactionSaved', { count: compaction.count, tokens: formatTokens(compaction.tokens_saved) })
                : t('compactionIdle')}
            </span>
          </div>
        )}

        {pruning.active && (
          <div className="flex items-center justify-between text-muted-foreground">
            <span>{t('pruning')}</span>
            <span className="tabular-nums text-foreground">
              {pruning.archived > 0 ? t('pruningArchived', { count: pruning.archived }) : t('pruningIdle')}
            </span>
          </div>
        )}

        {cache.active && (
          <div className="flex items-center justify-between text-muted-foreground">
            <span>{t('cache')}</span>
            <span className="tabular-nums text-foreground">
              {t('cacheHitRate', { rate: (cache.cache_hit_rate * 100).toFixed(0) })}
            </span>
          </div>
        )}

        {!compaction.active && !pruning.active && !cache.active && (
          <span className="text-muted-foreground">{t('allInactive')}</span>
        )}
      </div>

      {pruning.archive_restore_blocked_count > 0 && (
        <div className="mt-1 pt-1.5 border-t border-border/50 text-[10px] text-rose-600 dark:text-rose-400">
          {t('restoreBlocked', { count: pruning.archive_restore_blocked_count })}
        </div>
      )}

      <button
        type="button"
        onClick={onNavigateDetails}
        className="mt-1 pt-1.5 border-t border-border/50 text-[10px] text-primary-dark hover:text-primary-dark/80 dark:text-primary-light dark:hover:text-primary-light/80 text-left transition-colors"
      >
        {t('viewDetails')}
      </button>
    </div>
  );
}

export default function ContextUsageIndicator() {
  const t = useTranslations('chat.contextUsage');
  const isMobile = useIsMobile();
  const [panelOpen, setPanelOpen] = useState(false);
  const [contextHealth, setContextHealth] = useState<ContextHealth | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);

  const showContextUsage = useConfigStore((state) => state.showContextUsage);
  const messages = useChatStore(useShallow((state) => state.messages));
  const chatId = useChatStore(useShallow((state) => state.chatId ?? null));
  const setActiveSessionAnalyticsId = useChatStore((state) => state.setActiveSessionAnalyticsId);

  const contextBudget = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.role === 'assistant' && msg.contextBudget) {
        return msg.contextBudget;
      }
    }
    return null;
  }, [messages]);

  useEffect(() => {
    if (!panelOpen || !chatId) return;
    let cancelled = false;
    setLoadingHealth(true);
    getSessionAnalytics(chatId)
      .then((analytics) => {
        if (!cancelled) setContextHealth(analytics.context_health ?? null);
      })
      .catch(() => {
        if (!cancelled) setContextHealth(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingHealth(false);
      });
    return () => {
      cancelled = true;
    };
  }, [panelOpen, chatId]);

  const { percentage, displayUsage } = useMemo(() => {
    if (!contextBudget) return { percentage: 0, displayUsage: '0 / 0' };
    const pct = Math.min(contextBudget.usage_percent, 100);
    const display = `${formatTokens(contextBudget.current_tokens)} / ${formatTokens(contextBudget.max_context_tokens)}`;
    return { percentage: pct, displayUsage: display };
  }, [contextBudget]);

  const dotStatus = contextHealth
    ? resolveDisplayStatus(contextHealth)
    : budgetStatusToHealth(contextBudget?.health_status);

  if (!showContextUsage || !contextBudget || contextBudget.current_tokens === 0) {
    return null;
  }

  const strokeColor = percentage >= 90 ? '#ef4444' : percentage >= 75 ? '#f59e0b' : 'var(--primary-dark)';
  const textColor = getTextColorByUsage(percentage);

  const size = 16;
  const strokeWidth = 2.5;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  let warningText = '';
  if (percentage >= 90) {
    warningText = t('criticalWarning');
  } else if (percentage >= 75) {
    warningText = t('warning');
  }

  const handleNavigateDetails = () => {
    setPanelOpen(false);
    if (chatId) {
      setActiveSessionAnalyticsId(chatId);
    }
  };

  const ringElement = (
    <div
      className="relative inline-flex items-center justify-center cursor-pointer select-none p-1"
      role="status"
      aria-label={t('title')}
    >
      <svg width={size} height={size} className="rotate-[-90deg]" viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-muted-foreground/30"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          style={{ transition: 'stroke-dashoffset 0.3s ease' }}
        />
      </svg>
      {dotStatus !== 'inactive' && (
        <span
          className={`absolute top-0.5 right-0.5 w-[5px] h-[5px] rounded-full ring-1 ring-background ${STATUS_DOT_COLORS[dotStatus]}`}
          aria-hidden="true"
        />
      )}
    </div>
  );

  const panelContent = (
    <MiniPanelContent health={contextHealth} loading={loadingHealth} onNavigateDetails={handleNavigateDetails} />
  );

  const tooltipContent = (
    <div className="flex flex-col gap-1.5 py-1">
      <div className="flex items-center justify-between gap-4">
        <span className="font-medium text-foreground">{t('title')}</span>
        <span className={`${textColor} font-medium tabular-nums`}>
          {percentage.toFixed(1)}% &bull; {displayUsage}
        </span>
      </div>
      {warningText && (
        <div className={`mt-1 pt-1.5 border-t border-border/50 text-[11px] leading-relaxed ${textColor}`}>
          {warningText}
        </div>
      )}
    </div>
  );

  if (isMobile) {
    return (
      <TooltipProvider delayDuration={200}>
        <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
          <Tooltip>
            <TooltipTrigger asChild>
              <SheetTrigger asChild>{ringElement}</SheetTrigger>
            </TooltipTrigger>
            <TooltipContent side="top" className="!bg-white dark:!bg-gray-900 border shadow-lg text-xs max-w-xs">
              {tooltipContent}
            </TooltipContent>
          </Tooltip>
          <SheetContent side="bottom" className="max-h-[50vh] rounded-t-xl">
            <SheetHeader>
              <SheetTitle className="text-sm font-medium">{t('strategy.title')}</SheetTitle>
            </SheetHeader>
            {panelContent}
          </SheetContent>
        </Sheet>
      </TooltipProvider>
    );
  }

  return (
    <TooltipProvider delayDuration={200}>
      <Popover open={panelOpen} onOpenChange={setPanelOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>{ringElement}</PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="top" className="!bg-white dark:!bg-gray-900 border shadow-lg text-xs max-w-xs">
            {tooltipContent}
          </TooltipContent>
        </Tooltip>
        <PopoverContent side="top" align="center" className="w-auto p-0 border shadow-lg" sideOffset={8}>
          {panelContent}
        </PopoverContent>
      </Popover>
    </TooltipProvider>
  );
}
