'use client';

/**
 * [INPUT]
 * - react::{memo, useCallback}
 * - next-intl::useTranslations (POS: chat.topologyPruning 多语言字典)
 * - lucide-react::{Zap, GitFork, Cpu, ShieldCheck, Sparkles}
 * - @/lib/utils/classnameUtils::cn
 *
 * [OUTPUT]
 * - TopologyPruningIndicator: Model-tier adaptive topology pruning & token savings badge.
 *
 * [POS]
 * Composer header & execution HUD indicator component. Visualizes model intelligence tier,
 * adaptive single-agent folding state, and turn/token efficiency gains (DSH paradigm).
 */

import React, { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Zap, GitFork, Cpu, ShieldCheck, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type ModelIntelligenceTier = 'tier_1_sota_reasoning' | 'tier_2_strong_base' | 'tier_3_fast_light';
export type PruningStrategy = 'auto' | 'always_multi_agent' | 'direct_only';
export type PruningDecisionKind = 'direct_execution' | 'fanout_multi_agent' | 'hybrid_folded';

export interface TopologyPruningIndicatorProps {
  modelName: string;
  modelTier?: ModelIntelligenceTier;
  isFolded?: boolean;
  decision?: PruningDecisionKind;
  estimatedSavedTurns?: number;
  estimatedSavedTokens?: number;
  strategy?: PruningStrategy;
  onStrategyChange?: (strategy: PruningStrategy) => void;
  className?: string;
}

const TIER_BADGES: Record<ModelIntelligenceTier, { labelKey: string; colorClass: string }> = {
  tier_1_sota_reasoning: {
    labelKey: 'tier1Badge',
    colorClass: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
  },
  tier_2_strong_base: {
    labelKey: 'tier2Badge',
    colorClass: 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20',
  },
  tier_3_fast_light: {
    labelKey: 'tier3Badge',
    colorClass: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
  },
};

export const TopologyPruningIndicator = memo(function TopologyPruningIndicator({
  modelName,
  modelTier = 'tier_1_sota_reasoning',
  isFolded = true,
  decision = 'direct_execution',
  estimatedSavedTurns = 6,
  estimatedSavedTokens = 4800,
  strategy = 'auto',
  onStrategyChange,
  className,
}: TopologyPruningIndicatorProps) {
  const t = useTranslations('chat.topologyPruning');
  const tierConfig = TIER_BADGES[modelTier] || TIER_BADGES.tier_1_sota_reasoning;

  const handleStrategyClick = useCallback(
    (newStrategy: PruningStrategy) => {
      onStrategyChange?.(newStrategy);
    },
    [onStrategyChange]
  );

  return (
    <div
      data-testid="topology-pruning-indicator"
      className={cn(
        'flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 rounded-lg border text-xs select-none transition-colors',
        isFolded
          ? 'bg-emerald-500/5 dark:bg-emerald-950/20 border-emerald-500/20 dark:border-emerald-500/15'
          : 'bg-neutral-50 dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800',
        className
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span
          data-testid="model-tier-badge"
          className={cn(
            'inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border font-mono text-[10px] font-medium shrink-0',
            tierConfig.colorClass
          )}
        >
          <Cpu className="w-2.5 h-2.5" />
          {t(tierConfig.labelKey)}
        </span>

        <span className="font-mono text-[11px] text-neutral-600 dark:text-neutral-400 truncate max-w-[140px] sm:max-w-[200px]">
          {modelName}
        </span>

        {isFolded ? (
          <span
            data-testid="folded-savings-pill"
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/25 shrink-0"
          >
            <Zap className="w-3 h-3 text-emerald-500 shrink-0" />
            <span>
              {decision === 'hybrid_folded' ? t('hybridFolded') : t('directFolded')}
            </span>
            <span className="hidden sm:inline font-mono">
              ({t('savedTurnsTokens', { turns: estimatedSavedTurns, tokens: estimatedSavedTokens })})
            </span>
          </span>
        ) : (
          <span
            data-testid="fanout-pill"
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-neutral-200/60 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border border-neutral-300 dark:border-neutral-700 shrink-0"
          >
            <GitFork className="w-3 h-3 text-neutral-500 shrink-0" />
            {t('fanoutMode')}
          </span>
        )}
      </div>

      {/* Strategy selector chips */}
      <div className="flex items-center gap-1 shrink-0 ml-auto" data-testid="strategy-chips">
        <button
          type="button"
          data-testid="strategy-btn-auto"
          onClick={() => handleStrategyClick('auto')}
          className={cn(
            'px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors',
            strategy === 'auto'
              ? 'bg-neutral-900 text-white dark:bg-white dark:text-black font-semibold'
              : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
          )}
        >
          {t('strategyAuto')}
        </button>
        <button
          type="button"
          data-testid="strategy-btn-direct"
          onClick={() => handleStrategyClick('direct_only')}
          className={cn(
            'px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors',
            strategy === 'direct_only'
              ? 'bg-neutral-900 text-white dark:bg-white dark:text-black font-semibold'
              : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
          )}
        >
          {t('strategyDirect')}
        </button>
        <button
          type="button"
          data-testid="strategy-btn-fanout"
          onClick={() => handleStrategyClick('always_multi_agent')}
          className={cn(
            'px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors',
            strategy === 'always_multi_agent'
              ? 'bg-neutral-900 text-white dark:bg-white dark:text-black font-semibold'
              : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
          )}
        >
          {t('strategyMultiAgent')}
        </button>
      </div>
    </div>
  );
});

export default TopologyPruningIndicator;
