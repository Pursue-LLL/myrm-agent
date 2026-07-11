'use client';

/**
 * [INPUT]
 * - store/useChatStore::messages, chatId, setActiveSessionAnalyticsId (POS: Chat state management store.)
 * - store/useConfigStore::showContextUsage (POS: User configuration store.)
 * - services/statistics::getSessionAnalytics (POS: Statistics API client DTO layer.)
 * - services/chat::compactChat (POS: Chat service — manual context compaction.)
 * - services/contextHealth::ContextHealth, HealthStatus (POS: Statistics context-health DTO layer.)
 * - services/fork-api::forkConversation (POS: Fork API client — dynamic import in MiniPanel.)
 *
 * [OUTPUT]
 * - ContextUsageIndicator: token usage ring with strategy health dot and expandable mini panel with compress + fork actions.
 *
 * [POS]
 * Context usage and memory strategy indicator for the chat window.
 * Displays token usage ring, strategy health status dot, and on-click mini panel with compaction/pruning/cache details,
 * a manual "Compress context" button, and a conditional "Fork new topic" CTA (shown at ≥75% usage).
 */

import { useMemo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { getSessionAnalytics } from '@/services/statistics';
import { compactChat } from '@/services/chat';
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
  chatId: string | null;
  usagePercent: number;
  onNavigateDetails: () => void;
  onRefreshHealth: () => void;
}

function MiniPanelContent({ health, loading, chatId, usagePercent, onNavigateDetails, onRefreshHealth }: MiniPanelContentProps) {
  const t = useTranslations('chat.contextUsage.strategy');
  const [compacting, setCompacting] = useState(false);
  const [compactResult, setCompactResult] = useState<string | null>(null);
  const [compactError, setCompactError] = useState<string | null>(null);
  const [forking, setForking] = useState(false);

  const canCompress = !!chatId && usagePercent >= 30 && !compacting;

  const handleCompress = useCallback(async () => {
    if (!chatId || compacting) return;
    setCompacting(true);
    setCompactResult(null);
    setCompactError(null);
    try {
      const result = await compactChat(chatId);
      if (result.compacted) {
        setCompactResult(t('compressSuccess', { tokens: formatTokens(result.tokens_saved) }));
        onRefreshHealth();
      } else {
        setCompactResult(t('compressNotNeeded'));
      }
    } catch (err) {
      setCompactError(err instanceof Error ? err.message : t('compressError'));
    } finally {
      setCompacting(false);
    }
  }, [chatId, compacting, t, onRefreshHealth]);

  const canFork = !!chatId && usagePercent >= 75 && !forking;

  const handleFork = useCallback(async () => {
    if (!chatId || forking) return;
    setForking(true);
    try {
      const [{ forkConversation }, { default: workspaceStore }, { showI18nToast }] = await Promise.all([
        import('@/services/fork-api'),
        import('@/store/useWorkspaceStore'),
        import('@/services/i18nToastService'),
      ]);
      const response = await forkConversation(chatId, -1);
      if (response.success && response.data.new_chat_id) {
        showI18nToast('chat.fork.success', undefined, { type: 'success' });
        workspaceStore.getState().addPane(response.data.new_chat_id);
      } else {
        showI18nToast('chat.fork.failed', undefined, { type: 'error' });
      }
    } catch (e) {
      console.error('[ContextUsageFork]', e);
      try {
        const { showI18nToast } = await import('@/services/i18nToastService');
        showI18nToast('chat.fork.failed', undefined, { type: 'error' });
      } catch { /* toast import failed — already logged above */ }
    } finally {
      setForking(false);
    }
  }, [chatId, forking]);

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

      <div className="mt-1 pt-1.5 border-t border-border/50 flex flex-col gap-1.5">
        <button
          type="button"
          disabled={!canCompress}
          onClick={handleCompress}
          className={`w-full text-[11px] font-medium py-1.5 px-2 rounded-md transition-colors ${
            canCompress
              ? 'bg-primary-dark/10 text-primary-dark hover:bg-primary-dark/20 dark:bg-primary-light/10 dark:text-primary-light dark:hover:bg-primary-light/20'
              : 'bg-muted text-muted-foreground cursor-not-allowed'
          }`}
        >
          {compacting ? t('compressing') : t('compressContext')}
        </button>

        {compactResult && (
          <span className="text-[10px] text-emerald-600 dark:text-emerald-400">{compactResult}</span>
        )}
        {compactError && (
          <span className="text-[10px] text-rose-600 dark:text-rose-400">{compactError}</span>
        )}

        {canFork && (
          <button
            type="button"
            onClick={handleFork}
            disabled={forking}
            className="w-full text-[11px] font-medium py-1.5 px-2 rounded-md transition-colors bg-accent/60 text-accent-foreground hover:bg-accent dark:bg-accent/40 dark:hover:bg-accent/60"
          >
            {forking ? t('forking') : t('forkNewTopic')}
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onNavigateDetails}
        className="text-[10px] text-primary-dark hover:text-primary-dark/80 dark:text-primary-light dark:hover:text-primary-light/80 text-left transition-colors"
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

  const fetchHealth = useCallback(() => {
    if (!chatId) return;
    setLoadingHealth(true);
    getSessionAnalytics(chatId)
      .then((analytics) => setContextHealth(analytics.context_health ?? null))
      .catch(() => setContextHealth(null))
      .finally(() => setLoadingHealth(false));
  }, [chatId]);

  useEffect(() => {
    if (panelOpen && chatId) fetchHealth();
  }, [panelOpen, chatId, fetchHealth]);

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
    <MiniPanelContent
      health={contextHealth}
      loading={loadingHealth}
      chatId={chatId}
      usagePercent={percentage}
      onNavigateDetails={handleNavigateDetails}
      onRefreshHealth={fetchHealth}
    />
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
