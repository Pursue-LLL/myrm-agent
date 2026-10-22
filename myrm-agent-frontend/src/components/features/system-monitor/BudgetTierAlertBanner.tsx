import React, { useState } from 'react';
import { AdjustBudgetPayload, BudgetLadderVerdict } from './types';

export interface BudgetTierAlertBannerProps {
  verdict: BudgetLadderVerdict;
  onAdjustBudget?: (payload: AdjustBudgetPayload) => void;
  className?: string;
}

export const BudgetTierAlertBanner: React.FC<BudgetTierAlertBannerProps> = ({
  verdict,
  onAdjustBudget,
  className = '',
}) => {
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  if (verdict.tier === 'NORMAL') {
    return null;
  }

  const handleQuickAdd = async (tokens: number, costUsd: number) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onAdjustBudget?.({ added_tokens: tokens, added_cost_usd: costUsd });
    } finally {
      setIsSubmitting(false);
    }
  };

  const isSuspended = verdict.tier === 'TIER3_SUSPENDED';
  const isDegraded = verdict.tier === 'TIER2_DEGRADED';

  return (
    <div
      className={`rounded-lg p-3.5 border transition-all ${
        isSuspended
          ? 'bg-red-50 dark:bg-red-950/30 border-red-300 dark:border-red-900 text-red-900 dark:text-red-200'
          : isDegraded
          ? 'bg-amber-50 dark:bg-amber-950/30 border-amber-300 dark:border-amber-900 text-amber-900 dark:text-amber-200'
          : 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-900 text-blue-900 dark:text-blue-200'
      } ${className}`}
      data-testid="budget-tier-alert-banner"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="text-lg shrink-0">
            {isSuspended ? '🛑' : isDegraded ? '⚠️' : 'ℹ️'}
          </span>
          <div className="space-y-1">
            <div className="text-xs font-bold flex items-center gap-2">
              <span>
                {isSuspended
                  ? '阶段三：预算上限硬拦截（执行已安全挂起）'
                  : isDegraded
                  ? '阶段二：自适应降级截流生效中（80% 水位）'
                  : '阶段一：预算消耗进度提示（50% 水位）'}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-white/60 dark:bg-black/40">
                水位: {verdict.used_pct}%
              </span>
              {verdict.recommended_model_tier !== 'primary' && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-200 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200">
                  基座: {verdict.recommended_model_tier}
                </span>
              )}
            </div>
            <p className="text-xs opacity-90 leading-relaxed">{verdict.action_message}</p>
          </div>
        </div>

        {/* Quick CTA Actions */}
        {(isSuspended || isDegraded) && (
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => handleQuickAdd(50000, 2.5)}
              disabled={isSubmitting}
              className={`px-3 py-1.5 text-xs font-semibold rounded shadow-sm text-white transition-all ${
                isSuspended
                  ? 'bg-red-600 hover:bg-red-700 active:scale-95'
                  : 'bg-amber-600 hover:bg-amber-700 active:scale-95'
              } disabled:opacity-60`}
              data-testid="quick-add-budget-btn"
            >
              {isSubmitting ? '追加中...' : '+50k Token (追加 $2.5)'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
