'use client';

/**
 * [INPUT]
 * - store/useChatStore::messages, chatId, compactionRefreshNonce, setActiveSessionAnalyticsId (POS: Chat state management store.)
 * - store/useConfigStore::showContextUsage (POS: User configuration store.)
 * - ./useContextHealthPanel::useContextHealthPanel (POS: Panel open state and strategy health of the chat in view.)
 * - ./ContextStrategyPanel, ./ContextBreakdown, ./TurnGrowthSparkline (POS: Panel and tooltip sections.)
 * - ./contextUsageFormat (POS: Pure display helpers.)
 *
 * [OUTPUT]
 * - ContextUsageIndicator: token usage ring with strategy health dot, a token-breakdown tooltip and the strategy panel.
 *
 * [POS]
 * Context usage and memory strategy indicator for the chat window.
 * Displays the token usage ring and the strategy health status dot; hovering shows the token breakdown, clicking opens
 * the strategy panel (popover on desktop, bottom sheet on mobile).
 */

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import { useIsMobile } from '@/hooks/ui/useMediaQuery';
import { ContextBreakdown, hasContextBreakdown } from './ContextBreakdown';
import { ContextStrategyPanel } from './ContextStrategyPanel';
import TurnGrowthSparkline from './TurnGrowthSparkline';
import { useContextHealthPanel } from './useContextHealthPanel';
import { useContextWatermarkMetrics } from './useContextWatermarkMetrics';
import {
  STATUS_DOT_COLORS,
  budgetStatusToHealth,
  formatTokens,
  getTextColorByUsage,
  resolveDisplayStatus,
} from './contextUsageFormat';

export default function ContextUsageIndicator() {
  const t = useTranslations('chat.contextUsage');
  const isMobile = useIsMobile();

  const showContextUsage = useConfigStore((state) => state.showContextUsage);
  const messages = useChatStore(useShallow((state) => state.messages));
  const chatId = useChatStore(useShallow((state) => state.chatId ?? null));
  const compactionRefreshNonce = useChatStore((state) => state.compactionRefreshNonce);
  const setActiveSessionAnalyticsId = useChatStore((state) => state.setActiveSessionAnalyticsId);
  const watermarkMetrics = useContextWatermarkMetrics(messages);
  const {
    panelOpen,
    setPanelOpen,
    health: contextHealth,
    loading: loadingHealth,
  } = useContextHealthPanel(chatId, compactionRefreshNonce);

  const contextBudget = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.role === 'assistant' && msg.contextBudget) {
        return msg.contextBudget;
      }
    }
    return null;
  }, [messages]);

  const { percentage, displayUsage } = useMemo(() => {
    if (!contextBudget) {
      return { percentage: 0, displayUsage: '0 / 0' };
    }
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
    <output
      data-testid="context-usage-indicator"
      className="relative inline-flex items-center justify-center cursor-pointer select-none p-1"
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
    </output>
  );

  const panelContent = (
    <ContextStrategyPanel
      health={contextHealth}
      loading={loadingHealth}
      chatId={chatId}
      usagePercent={percentage}
      contextBudget={contextBudget}
      watermarkMetrics={watermarkMetrics}
      onNavigateDetails={handleNavigateDetails}
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
      {contextBudget && hasContextBreakdown(contextBudget) ? (
        <ContextBreakdown budget={contextBudget} className="pt-1 border-t border-border/40" />
      ) : null}
      {watermarkMetrics.historyTurnTokens.length > 0 ? (
        <TurnGrowthSparkline metrics={watermarkMetrics} width={200} height={32} className="mt-1" />
      ) : null}
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
          {/* A phone is shorter than the panel; the sheet scrolls so the compress control below the fold stays reachable. */}
          <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto rounded-t-xl">
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
        {/* Radix sizes the popover to its widest line, so `w-auto` would stretch the card to the longest hint. */}
        <PopoverContent side="top" align="center" className="w-80 p-0 border shadow-lg" sideOffset={8}>
          {panelContent}
        </PopoverContent>
      </Popover>
    </TooltipProvider>
  );
}
