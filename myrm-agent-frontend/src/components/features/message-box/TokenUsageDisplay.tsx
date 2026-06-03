'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  TokenUsage,
  TokenEconomicsSnapshot,
  type ContextBudget,
  type CostStatus,
  type SensitivityLevel,
} from '@/store/chat/types';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useConfigStore from '@/store/useConfigStore';
import { isLocalMode } from '@/lib/deploy-mode';
import { getSessionAnalytics, type SessionAnalytics } from '@/services/statistics';
import useChatStore from '@/store/useChatStore';

const IconProps = 'w-3 h-3';

const CoinsIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="8" cy="8" r="6" />
    <path d="M18.09 10.37A6 6 0 1 1 10.34 18" />
    <path d="M7 6h1v4" />
    <path d="m16.71 13.88.7.71-2.82 2.82" />
  </svg>
);

const ArrowUpRightIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M7 17 17 7" />
    <path d="M7 7h10v10" />
  </svg>
);

const ArrowDownRightIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="m7 7 10 10" />
    <path d="M17 7v10H7" />
  </svg>
);

const DatabaseIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M3 5v14a9 3 0 0 0 18 0V5" />
    <path d="M3 12a9 3 0 0 0 18 0" />
  </svg>
);

const BrainIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
    <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
    <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4" />
    <path d="M12 18v4" />
  </svg>
);

const QuoteIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V21z" />
    <path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3c0 1 0 1 1 1z" />
  </svg>
);

interface TokenUsageDisplayProps {
  chatId?: string;
  messageId?: string;
  usage: TokenUsage;
  tokenEconomics?: TokenEconomicsSnapshot;
  costUsd?: number;
  costStatus?: CostStatus;
  cacheBreakReason?: string;
  cacheSuggestedActions?: string;
  modelName?: string;
  routingTier?: 'simple' | 'standard' | 'reasoning' | 'complex';
  privacyLevel?: SensitivityLevel;
  privacyAction?: string;
  privacyRoute?: string;
  contextBudget?: ContextBudget;
}

function formatTokens(tokens: number): string {
  if (tokens >= 1000000) {
    return `${(tokens / 1000000).toFixed(1)}M`;
  }
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}k`;
  }
  return tokens.toString();
}

function calculateCacheSavings(usage: TokenUsage): number {
  if (!usage.cached_tokens || usage.prompt_tokens === 0) return 0;
  return Math.round((usage.cached_tokens / usage.prompt_tokens) * 100);
}

function formatCost(cost: number): string {
  if (cost < 0.0001) return `<$0.0001`;
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

function formatModelName(model: string): string {
  const parts = model.split('/');
  return parts[parts.length - 1];
}

const BUDGET_COLORS = {
  healthy: {
    stroke: 'rgb(34, 197, 94)',
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
    text: 'text-emerald-600 dark:text-emerald-400',
    barBg: 'bg-emerald-500',
  },
  warning: {
    stroke: 'rgb(245, 158, 11)',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-600 dark:text-amber-400',
    barBg: 'bg-amber-500',
  },
  critical: {
    stroke: 'rgb(239, 68, 68)',
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-600 dark:text-red-400',
    barBg: 'bg-red-500',
  },
} as const;

function ContextRing({ budget, size = 20 }: { budget: ContextBudget; size?: number }) {
  const strokeWidth = 2.5;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(budget.usage_percent, 100));
  const strokeDashoffset = circumference - (progress / 100) * circumference;
  const colors = BUDGET_COLORS[budget.health_status];

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{ transform: 'rotate(-90deg)' }}
      aria-hidden="true"
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        className="text-black/10 dark:text-white/10"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={colors.stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        className="transition-all duration-500 ease-out"
      />
    </svg>
  );
}

export default function TokenUsageDisplay({
  chatId,
  messageId,
  usage,
  tokenEconomics,
  costUsd,
  costStatus,
  cacheBreakReason,
  cacheSuggestedActions,
  modelName,
  routingTier,
  privacyLevel,
  privacyAction,
  privacyRoute,
  contextBudget,
}: TokenUsageDisplayProps) {
  const t = useTranslations('chat.tokenUsage');
  const enableCostEstimation = useConfigStore((state) => state.enableCostEstimation);

  const [tooltipOpen, setTooltipOpen] = useState(false);
  const [sessionAnalytics, setSessionAnalytics] = useState<SessionAnalytics | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const setActiveSessionAnalyticsId = useChatStore((state) => state.setActiveSessionAnalyticsId);
  const setActiveSessionAnalyticsMessageId = useChatStore((state) => state.setActiveSessionAnalyticsMessageId);

  const renderDelta = useCallback(
    (current: number, average: number, isLowerBetter: boolean, thresholdPct = 10, absThreshold = 50) => {
      if (!average || average <= 0 || !current || current <= 0) return null;
      const diff = current - average;
      const pct = (diff / average) * 100;

      const isBetter = isLowerBetter ? diff < 0 : diff > 0;

      // Check thresholds to avoid micro jitter
      const absDiff = Math.abs(diff);
      const absPct = Math.abs(pct);

      if (absPct < thresholdPct || (isLowerBetter && absDiff < absThreshold)) {
        return (
          <span className="text-[9px] px-1 py-0.5 rounded font-mono bg-muted text-muted-foreground" title="Consistent">
            ~
          </span>
        );
      }

      if (isBetter) {
        return (
          <span
            className="text-[9px] px-1.5 py-0.5 rounded font-mono font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            title={`${Math.round(absPct)}% better`}
          >
            {isLowerBetter ? '-' : '+'}
            {Math.round(absPct)}%
          </span>
        );
      }

      return (
        <span
          className="text-[9px] px-1.5 py-0.5 rounded font-mono font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400"
          title={`${Math.round(absPct)}% worse`}
        >
          {isLowerBetter ? '+' : '-'}
          {Math.round(absPct)}%
        </span>
      );
    },
    [],
  );

  useEffect(() => {
    let active = true;
    if (tooltipOpen && chatId) {
      const fetchAnalytics = async () => {
        try {
          setLoadingAnalytics(true);
          const data = await getSessionAnalytics(chatId);
          if (active) {
            setSessionAnalytics(data);
          }
        } catch (error) {
          console.error('Failed to fetch session analytics inside tooltip:', error);
        } finally {
          if (active) {
            setLoadingAnalytics(false);
          }
        }
      };
      fetchAnalytics();
    }
    return () => {
      active = false;
    };
  }, [tooltipOpen, chatId]);

  if (!isLocalMode()) {
    return null;
  }

  if (!enableCostEstimation || !usage || usage.total_tokens === 0) {
    return null;
  }

  const hasCachedTokens = usage.cached_tokens !== undefined && usage.cached_tokens > 0;
  const hasReasoningTokens = usage.reasoning_tokens !== undefined && usage.reasoning_tokens > 0;
  const hasCitationTokens = usage.citation_tokens !== undefined && usage.citation_tokens > 0;
  const cacheSavings = calculateCacheSavings(usage);
  const budgetColors = contextBudget ? BUDGET_COLORS[contextBudget.health_status] : null;

  return (
    <TooltipProvider>
      <Tooltip open={tooltipOpen} onOpenChange={setTooltipOpen}>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-1 px-2 py-1 text-black/70 dark:text-white/70 rounded-xl hover:bg-light-secondary dark:hover:bg-dark-secondary active:scale-95 transition duration-200 hover:text-black dark:hover:text-white"
            aria-label={
              contextBudget
                ? `${contextBudget.usage_percent.toFixed(1)}% ${t('contextUsed')}`
                : `${formatTokens(usage.total_tokens)} tokens`
            }
          >
            {contextBudget ? <ContextRing budget={contextBudget} /> : <CoinsIcon className="w-4 h-4" />}
            <span className="text-xs font-medium tabular-nums">
              {contextBudget ? `${Math.round(contextBudget.usage_percent)}%` : formatTokens(usage.total_tokens)}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="p-0 overflow-hidden !bg-white dark:!bg-gray-900 border shadow-lg">
          <div className="min-w-[220px]">
            {/* 标题栏 */}
            <div className="px-3 py-2 bg-secondary dark:bg-muted border-b border-border">
              <span className="text-sm font-semibold text-foreground">{t('title')}</span>
            </div>

            {/* 上下文预算可视化 */}
            {contextBudget && budgetColors && (
              <div className="px-3 pt-3 pb-1">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-muted-foreground">{t('contextWindow')}</span>
                  <span className="text-xs font-mono font-medium tabular-nums">
                    {formatTokens(contextBudget.current_tokens)} / {formatTokens(contextBudget.max_context_tokens)}
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ease-out ${budgetColors.barBg}`}
                    style={{ width: `${Math.min(contextBudget.usage_percent, 100)}%` }}
                  />
                </div>
                {contextBudget.health_status !== 'healthy' && (
                  <div
                    className={`mt-2 rounded-full px-2 py-1.5 text-[11px] leading-tight ${budgetColors.bg} ${budgetColors.text}`}
                  >
                    {contextBudget.health_status === 'critical' ? t('contextCritical') : t('contextWarning')}
                  </div>
                )}
                <div className="h-px bg-border mt-2.5" />
              </div>
            )}

            {/* 详细数据 */}
            <div className="p-3 space-y-2.5">
              {/* 输入 Token */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded flex items-center justify-center bg-blue-100 dark:bg-blue-900/40">
                    <ArrowUpRightIcon className={`${IconProps} text-blue-600 dark:text-blue-400`} />
                  </div>
                  <span className="text-xs text-muted-foreground">{t('inputTokens')}</span>
                </div>
                <span className="text-xs font-mono font-medium tabular-nums">
                  {usage.prompt_tokens.toLocaleString()}
                </span>
              </div>

              {/* 输出 Token */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded flex items-center justify-center bg-purple-100 dark:bg-purple-900/40">
                    <ArrowDownRightIcon className={`${IconProps} text-purple-600 dark:text-purple-400`} />
                  </div>
                  <span className="text-xs text-muted-foreground">{t('outputTokens')}</span>
                </div>
                <span className="text-xs font-mono font-medium tabular-nums">
                  {usage.completion_tokens.toLocaleString()}
                </span>
              </div>

              {/* 推理 Token */}
              {hasReasoningTokens && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded flex items-center justify-center bg-amber-100 dark:bg-amber-900/40">
                      <BrainIcon className={`${IconProps} text-amber-600 dark:text-amber-400`} />
                    </div>
                    <span className="text-xs text-muted-foreground">{t('reasoningTokens')}</span>
                  </div>
                  <span className="text-xs font-mono font-medium tabular-nums text-amber-600 dark:text-amber-400">
                    {usage.reasoning_tokens!.toLocaleString()}
                  </span>
                </div>
              )}

              {/* 缓存命中 Token */}
              {hasCachedTokens && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded flex items-center justify-center bg-emerald-100 dark:bg-emerald-900/40">
                      <DatabaseIcon className={`${IconProps} text-emerald-600 dark:text-emerald-400`} />
                    </div>
                    <span className="text-xs text-muted-foreground">{t('cachedTokens')}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono font-medium tabular-nums text-emerald-600 dark:text-emerald-400">
                      {usage.cached_tokens!.toLocaleString()}
                    </span>
                    <span className="text-[10px] px-1 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400 font-medium">
                      -{cacheSavings}%
                    </span>
                    {tokenEconomics?.total_cache_savings_usd !== undefined &&
                      (tokenEconomics.total_cache_savings_usd < 0 ? (
                        <span className="text-[10px] px-1 py-0.5 rounded bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400 font-medium">
                          -${Math.abs(tokenEconomics.total_cache_savings_usd).toFixed(4)}
                        </span>
                      ) : tokenEconomics.total_cache_savings_usd > 0 ? (
                        <span className="text-[10px] px-1 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400 font-medium">
                          +${tokenEconomics.total_cache_savings_usd.toFixed(4)}
                        </span>
                      ) : null)}
                  </div>
                </div>
              )}

              {/* Cache break 归因 + 行动建议 */}
              {!hasCachedTokens && cacheBreakReason && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center justify-between cursor-help">
                        <div className="flex items-center gap-2">
                          <div className="w-5 h-5 rounded flex items-center justify-center bg-amber-100 dark:bg-amber-900/40">
                            <DatabaseIcon className={`${IconProps} text-amber-600 dark:text-amber-400`} />
                          </div>
                          <span className="text-xs text-muted-foreground">{t('cacheReset')}</span>
                        </div>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400 font-medium max-w-[160px] truncate">
                          {cacheBreakReason}
                        </span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-[300px]">
                      <p className="text-xs font-medium">{cacheBreakReason}</p>
                      {cacheSuggestedActions && (
                        <p className="text-xs text-muted-foreground mt-1">{cacheSuggestedActions}</p>
                      )}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}

              {/* 引用 Token */}
              {hasCitationTokens && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded flex items-center justify-center bg-sky-100 dark:bg-sky-900/40">
                      <QuoteIcon className={`${IconProps} text-sky-600 dark:text-sky-400`} />
                    </div>
                    <span className="text-xs text-muted-foreground">{t('citationTokens')}</span>
                  </div>
                  <span className="text-xs font-mono font-medium tabular-nums text-sky-600 dark:text-sky-400">
                    {usage.citation_tokens!.toLocaleString()}
                  </span>
                </div>
              )}

              {/* 分隔线 */}
              <div className="h-px bg-border my-1" />

              {/* 总计 Token */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded flex items-center justify-center bg-primary/15 dark:bg-primary/25">
                    <CoinsIcon className={`${IconProps} text-primary`} />
                  </div>
                  <span className="text-xs font-medium text-foreground">{t('totalTokens')}</span>
                </div>
                <span className="text-xs font-mono font-semibold tabular-nums">{formatTokens(usage.total_tokens)}</span>
              </div>

              {/* 费用 */}
              {costUsd !== undefined && costUsd > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{t('cost')}</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono font-medium tabular-nums">{formatCost(costUsd)}</span>
                    {costStatus && costStatus !== 'unknown' && (
                      <span
                        className={`text-[10px] px-1 py-0.5 rounded font-medium ${
                          costStatus === 'actual'
                            ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400'
                            : 'bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400'
                        }`}
                      >
                        {t(costStatus === 'actual' ? 'costActual' : 'costEstimated')}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* 模型 */}
              {modelName && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{t('model')}</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono text-muted-foreground truncate max-w-[120px]">
                      {formatModelName(modelName)}
                    </span>
                    {routingTier && (
                      <span
                        className={`text-[10px] px-1 py-0.5 rounded font-medium ${
                          routingTier === 'simple'
                            ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400'
                            : routingTier === 'reasoning'
                              ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400'
                              : 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                        }`}
                      >
                        {t(
                          routingTier === 'simple'
                            ? 'routingSimple'
                            : routingTier === 'reasoning'
                              ? 'routingReasoning'
                              : 'routingStandard',
                        )}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Privacy Level */}
              {privacyLevel && privacyLevel !== 's1' && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{t('privacyLevel')}</span>
                  <div className="flex items-center gap-1">
                    {privacyAction === 'pseudonymize' && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400">
                        {t('privacyPseudonymized')}
                      </span>
                    )}
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                        privacyLevel === 's3'
                          ? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400'
                          : 'bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400'
                      }`}
                    >
                      {privacyLevel === 's3' ? t('privacyS3') : t('privacyS2')}
                    </span>
                  </div>
                </div>
              )}

              {/* Privacy Route */}
              {privacyRoute && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{t('privacyRoute')}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      privacyRoute.includes('local')
                        ? 'bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400'
                        : 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                    }`}
                  >
                    {privacyRoute.includes('local') ? t('privacyRouteLocal') : t('privacyRouteCloud')}
                  </span>
                </div>
              )}
              {/* 细粒度成本分解 */}
              {tokenEconomics?.model_breakdown && Object.keys(tokenEconomics.model_breakdown).length > 0 && (
                <>
                  <div className="h-px bg-border my-1" />
                  <div className="px-1 py-0.5 bg-secondary/50 dark:bg-muted/50 rounded flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-foreground uppercase tracking-wider">
                      {t('modelBreakdown')}
                    </span>
                  </div>
                  {Object.entries(tokenEconomics.model_breakdown).map(([model, data]) => (
                    <div key={model} className="flex items-center justify-between text-[11px] pl-1">
                      <span className="text-muted-foreground truncate max-w-[120px]" title={model}>
                        {formatModelName(model)}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-muted-foreground">{formatTokens(data.total_tokens)}t</span>
                        <span className="font-mono font-medium text-foreground w-[40px] text-right">
                          {formatCost(data.cost_usd)}
                        </span>
                      </div>
                    </div>
                  ))}
                </>
              )}

              {tokenEconomics?.tool_breakdown && Object.keys(tokenEconomics.tool_breakdown).length > 0 && (
                <>
                  <div className="h-px bg-border my-1" />
                  <div className="px-1 py-0.5 bg-secondary/50 dark:bg-muted/50 rounded flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-foreground uppercase tracking-wider">
                      {t('toolBreakdown')}
                    </span>
                  </div>
                  {Object.entries(tokenEconomics.tool_breakdown).map(([tool, data]) => (
                    <div key={tool} className="flex items-center justify-between text-[11px] pl-1">
                      <span className="text-muted-foreground truncate max-w-[120px]" title={tool}>
                        {tool}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-muted-foreground">{formatTokens(data.total_tokens)}t</span>
                        <span className="font-mono font-medium text-foreground w-[40px] text-right">
                          {formatCost(data.cost_usd)}
                        </span>
                      </div>
                    </div>
                  ))}
                </>
              )}

              {/* 细粒度性能分解 */}
              {tokenEconomics?.latency && (
                <>
                  <div className="h-px bg-border my-1" />
                  <div className="px-1 py-0.5 bg-secondary/50 dark:bg-muted/50 rounded flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-foreground uppercase tracking-wider">
                      {t('performance')}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 pl-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">TTFT Avg</span>
                      <span className="font-mono text-foreground">
                        {tokenEconomics.latency.avg_ttft_ms > 0
                          ? `${Math.round(tokenEconomics.latency.avg_ttft_ms)}ms`
                          : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">P95</span>
                      <span className="font-mono text-foreground">
                        {tokenEconomics.latency.p95_ms > 0 ? `${Math.round(tokenEconomics.latency.p95_ms)}ms` : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">TPS</span>
                      <span className="font-mono text-foreground">
                        {tokenEconomics.latency.avg_tokens_per_second > 0
                          ? `${Math.round(tokenEconomics.latency.avg_tokens_per_second)}/s`
                          : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">Calls</span>
                      <span className="font-mono text-foreground">{tokenEconomics.call_count}</span>
                    </div>
                  </div>
                </>
              )}

              {/* 性能诊断比对与会话性能基线 */}
              {chatId && tokenEconomics?.latency && (
                <>
                  <div className="h-px bg-border my-1" />
                  <div className="px-1 py-0.5 bg-secondary/50 dark:bg-muted/50 rounded flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-foreground uppercase tracking-wider">
                      {t('sessionBaseline')}
                    </span>
                  </div>
                  {loadingAnalytics ? (
                    <div className="space-y-2 pl-1 pt-2 animate-pulse">
                      <div className="flex items-center justify-between">
                        <div className="h-3 bg-muted-foreground/15 rounded w-16" />
                        <div className="flex items-center gap-1.5">
                          <div className="h-2.5 bg-muted-foreground/10 rounded w-8" />
                          <div className="h-2.5 bg-muted-foreground/5 rounded w-3" />
                          <div className="h-2.5 bg-muted-foreground/15 rounded w-8" />
                          <div className="h-3 bg-muted-foreground/10 rounded w-6" />
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="h-3 bg-muted-foreground/15 rounded w-20" />
                        <div className="flex items-center gap-1.5">
                          <div className="h-2.5 bg-muted-foreground/10 rounded w-8" />
                          <div className="h-2.5 bg-muted-foreground/5 rounded w-3" />
                          <div className="h-2.5 bg-muted-foreground/15 rounded w-8" />
                          <div className="h-3 bg-muted-foreground/10 rounded w-6" />
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="h-3 bg-muted-foreground/15 rounded w-14" />
                        <div className="flex items-center gap-1.5">
                          <div className="h-2.5 bg-muted-foreground/10 rounded w-8" />
                          <div className="h-2.5 bg-muted-foreground/5 rounded w-3" />
                          <div className="h-2.5 bg-muted-foreground/15 rounded w-8" />
                          <div className="h-3 bg-muted-foreground/10 rounded w-6" />
                        </div>
                      </div>
                      <div className="pt-2">
                        <div className="h-7 bg-primary/5 rounded w-full" />
                      </div>
                    </div>
                  ) : sessionAnalytics?.token_economics?.latency ? (
                    <div className="space-y-2 pl-1 pt-1.5">
                      {/* TTFT comparison */}
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-muted-foreground">{t('avgTtft')}</span>
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono text-muted-foreground text-[10px]" title={t('currentMsg')}>
                            {Math.round(tokenEconomics.latency.avg_ttft_ms)}ms
                          </span>
                          <span className="text-muted-foreground text-[10px]">vs</span>
                          <span className="font-mono font-semibold text-foreground mr-1" title={t('historyAvg')}>
                            {Math.round(sessionAnalytics.token_economics.latency.avg_ttft_ms)}ms
                          </span>
                          {renderDelta(
                            tokenEconomics.latency.avg_ttft_ms,
                            sessionAnalytics.token_economics.latency.avg_ttft_ms,
                            true,
                          )}
                        </div>
                      </div>
                      {/* TPS comparison */}
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-muted-foreground">{t('avgTps')}</span>
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono text-muted-foreground text-[10px]" title={t('currentMsg')}>
                            {Math.round(tokenEconomics.latency.avg_tokens_per_second)}/s
                          </span>
                          <span className="text-muted-foreground text-[10px]">vs</span>
                          <span className="font-mono font-semibold text-foreground mr-1" title={t('historyAvg')}>
                            {Math.round(sessionAnalytics.token_economics.latency.avg_tokens_per_second)}/s
                          </span>
                          {renderDelta(
                            tokenEconomics.latency.avg_tokens_per_second,
                            sessionAnalytics.token_economics.latency.avg_tokens_per_second,
                            false,
                          )}
                        </div>
                      </div>
                      {/* Latency comparison */}
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-muted-foreground">{t('avgLatency')}</span>
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono text-muted-foreground text-[10px]" title={t('currentMsg')}>
                            {Math.round(tokenEconomics.latency.avg_ms)}ms
                          </span>
                          <span className="text-muted-foreground text-[10px]">vs</span>
                          <span className="font-mono font-semibold text-foreground mr-1" title={t('historyAvg')}>
                            {Math.round(sessionAnalytics.token_economics.latency.avg_ms)}ms
                          </span>
                          {renderDelta(
                            tokenEconomics.latency.avg_ms,
                            sessionAnalytics.token_economics.latency.avg_ms,
                            true,
                            10,
                            100,
                          )}
                        </div>
                      </div>

                      {/* View Trace Button Link */}
                      <div className="pt-2">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setTooltipOpen(false);
                            if (messageId) {
                              setActiveSessionAnalyticsMessageId(messageId);
                            }
                            setActiveSessionAnalyticsId(chatId);
                          }}
                          className="w-full flex items-center justify-center gap-1 py-1.5 px-2 bg-primary/10 hover:bg-primary/20 text-primary rounded text-[11px] font-medium transition duration-200"
                        >
                          <span>{t('viewTrace')}</span>
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="w-3 h-3"
                          >
                            <path d="M5 12h14" />
                            <path d="m12 5 7 7-7 7" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-[10px] text-muted-foreground text-center py-2">{t('noSessionStats')}</div>
                  )}
                </>
              )}
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
