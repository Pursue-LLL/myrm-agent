/**
 * [INPUT]: metrics (CacheSavingsMetrics), guardEvaluation (BudgetGuardEvaluation), driftAlert (CostDriftAlert).
 * [OUTPUT]: High-ROI visual HUD with 99% cache savings badge, actual vs baseline cost gauge, runaway guard alarms, and drift drawer trigger.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/CacheSavingsRoiHUD.tsx
 */

import React, { useState } from 'react';
import { CostDriftExplainerDrawer } from './CostDriftExplainerDrawer';
import {
  BudgetGuardEvaluation,
  CacheSavingsMetrics,
  CostDriftAlert,
} from './tokenEconomicsTypes';

export interface CacheSavingsRoiHUDProps {
  metrics: CacheSavingsMetrics;
  guardEvaluation?: BudgetGuardEvaluation | null;
  driftAlert?: CostDriftAlert | null;
  onAdjustBudget?: () => void;
  onTogglePause?: (paused: boolean) => void;
}

export const CacheSavingsRoiHUD: React.FC<CacheSavingsRoiHUDProps> = ({
  metrics,
  guardEvaluation,
  driftAlert,
  onAdjustBudget,
  onTogglePause,
}) => {
  const [isDriftDrawerOpen, setIsDriftDrawerOpen] = useState<boolean>(false);

  const isTripped = guardEvaluation?.status === 'CIRCUIT_BREAKER_TRIPPED';
  const isWarning = guardEvaluation?.status === 'SOFT_WARNING';

  return (
    <div
      className="p-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm space-y-4"
      data-testid="cache-savings-roi-hud"
    >
      {/* 99% Cache Savings High-ROI Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-gradient-to-r from-emerald-500/10 via-teal-500/10 to-blue-500/10 border border-emerald-500/20 dark:border-emerald-500/30 rounded-lg">
        <div className="flex items-center gap-2.5">
          <span className="text-2xl" role="img" aria-label="target">
            🎯
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                99% 缓存节流真实收益
              </span>
              <span
                className="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200 rounded-full"
                data-testid="cache-hit-badge"
              >
                命中率 {metrics.cache_hit_rate_pct}%
              </span>
            </div>
            <div
              className="text-sm sm:text-base font-bold text-gray-900 dark:text-gray-100 mt-0.5"
              data-testid="savings-headline"
            >
              已为您净节省 <span className="text-emerald-600 dark:text-emerald-400">¥{metrics.saved_amount_rmb.toFixed(2)}</span>{' '}
              <span className="text-xs text-gray-500 dark:text-gray-400 font-normal">
                ({metrics.saved_percentage}% 账单减免)
              </span>
            </div>
          </div>
        </div>

        {driftAlert && (
          <button
            type="button"
            onClick={() => setIsDriftDrawerOpen(true)}
            className="px-2.5 py-1 text-xs border border-gray-300 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-gray-700 dark:text-gray-300 transition-colors flex items-center gap-1 self-start sm:self-center"
            data-testid="open-drift-drawer-btn"
          >
            <span>📈 单位成本漂移</span>
            {driftAlert.is_significant_drift && (
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            )}
          </button>
        )}
      </div>

      {/* Main Comparative Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-gray-400 text-[10px]">原始无缓存基准</div>
          <div
            className="text-sm font-semibold text-gray-500 line-through mt-0.5"
            data-testid="baseline-cost"
          >
            ¥{metrics.baseline_cost_rmb.toFixed(4)}
          </div>
          <div className="text-[10px] text-gray-400">若全量硬跑</div>
        </div>

        <div className="p-3 bg-emerald-50/40 dark:bg-emerald-950/20 rounded-lg border border-emerald-100 dark:border-emerald-900/40">
          <div className="text-emerald-600 dark:text-emerald-400 text-[10px]">实付算力支出</div>
          <div
            className="text-base font-bold text-gray-900 dark:text-gray-100 mt-0.5"
            data-testid="actual-cost"
          >
            ¥{metrics.actual_cost_rmb.toFixed(4)}
          </div>
          <div className="text-[10px] text-emerald-600 dark:text-emerald-400">已享缓存折扣</div>
        </div>

        <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-gray-400 text-[10px]">实时燃速速率</div>
          <div
            className="text-sm font-semibold text-gray-800 dark:text-gray-200 mt-0.5"
            data-testid="burn-rate"
          >
            ¥{metrics.burn_rate_rmb_per_minute.toFixed(2)} / min
          </div>
          <div className="text-[10px] text-gray-400">模型: {metrics.model_name}</div>
        </div>

        <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-gray-400 text-[10px]">算力防刺客状态</div>
          <div className="mt-0.5 flex items-center gap-1.5" data-testid="guard-status">
            {isTripped ? (
              <span className="font-bold text-red-600 dark:text-red-400">🛑 熔断刹车</span>
            ) : isWarning ? (
              <span className="font-semibold text-amber-600 dark:text-amber-400">⚠️ 软预警</span>
            ) : (
              <span className="font-semibold text-emerald-600 dark:text-emerald-400">✓ 正常护航</span>
            )}
          </div>
          <div className="text-[10px] text-gray-400">单任务防跑飞</div>
        </div>
      </div>

      {/* Circuit breaker / runaway warning alert box */}
      {guardEvaluation && guardEvaluation.status !== 'OK' && (
        <div
          className={`p-3 rounded-lg border text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 ${
            isTripped
              ? 'bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'
              : 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300'
          }`}
          data-testid="guard-alert-box"
        >
          <div className="space-y-0.5">
            <div className="font-semibold">{guardEvaluation.reason}</div>
            <div className="text-[11px] opacity-90">{guardEvaluation.suggested_action}</div>
          </div>
          <div className="flex items-center gap-2 self-end sm:self-center">
            {isTripped && (
              <button
                type="button"
                onClick={() => onTogglePause?.(false)}
                className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-medium transition-colors"
                data-testid="resume-execution-btn"
              >
                强制放行恢复
              </button>
            )}
            {onAdjustBudget && (
              <button
                type="button"
                onClick={onAdjustBudget}
                className="px-3 py-1 bg-gray-800 hover:bg-gray-700 dark:bg-gray-700 dark:hover:bg-gray-600 text-white rounded text-xs font-medium transition-colors"
                data-testid="adjust-budget-btn"
              >
                追加配额
              </button>
            )}
          </div>
        </div>
      )}

      {/* Drawer */}
      <CostDriftExplainerDrawer
        isOpen={isDriftDrawerOpen}
        onClose={() => setIsDriftDrawerOpen(false)}
        alert={driftAlert || null}
      />
    </div>
  );
};
