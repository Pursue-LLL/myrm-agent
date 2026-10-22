/**
 * [INPUT]
 * - ledger: CumulativeDeliveryLedgerData | null 整轮交付累计账本数据
 * - onAdjustBudget?: (payload: AdjustDeliveryBudgetPayload) => Promise<void> 追加预算或恢复回调
 * - loading?: boolean 加载状态
 *
 * [OUTPUT]
 * - CumulativeDeliveryLedgerCard: 整轮交付全生命周期成本核算与未知用量审计大盘卡片
 *
 * [POS]
 * src/components/features/system-monitor/CumulativeDeliveryLedgerCard.tsx — 整轮交付双账本与硬预算熔断大盘
 */

import React, { useState } from 'react';
import type {
  AdjustDeliveryBudgetPayload,
  CumulativeDeliveryLedgerData,
} from './deliveryBudgetTypes';
import { TrialLedgerBreakdownTable } from './TrialLedgerBreakdownTable';

export interface CumulativeDeliveryLedgerCardProps {
  ledger: CumulativeDeliveryLedgerData | null;
  onAdjustBudget?: (payload: AdjustDeliveryBudgetPayload) => Promise<void>;
  loading?: boolean;
  className?: string;
}

export const CumulativeDeliveryLedgerCard: React.FC<CumulativeDeliveryLedgerCardProps> = ({
  ledger,
  onAdjustBudget,
  loading = false,
  className = '',
}) => {
  const [showBreakdown, setShowBreakdown] = useState(false);
  const [isAdjusting, setIsAdjusting] = useState(false);

  if (!ledger) {
    return (
      <div
        data-testid="delivery-ledger-loading"
        className={`p-5 rounded-xl border border-slate-800 bg-slate-900/80 text-slate-400 flex items-center space-x-3 ${className}`}
      >
        <div className="w-4 h-4 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
        <span className="text-xs">正在载入多智能体整轮交付累计账本...</span>
      </div>
    );
  }

  const {
    delivery_id,
    title,
    budget_tokens_limit,
    total_metered_tokens,
    total_imputed_tokens,
    total_effective_tokens,
    total_metered_cost_usd,
    total_imputed_cost_usd,
    total_effective_cost_usd,
    unmetered_trials_count,
    total_trials_count,
    gate_verdict,
    is_paused,
    pause_reason,
    trials,
  } = ledger;

  const usagePercent =
    budget_tokens_limit && budget_tokens_limit > 0
      ? Math.min(100, Math.round((total_effective_tokens / budget_tokens_limit) * 100))
      : null;

  const handleQuickAddBudget = async () => {
    if (!onAdjustBudget || isAdjusting) return;
    try {
      setIsAdjusting(true);
      await onAdjustBudget({
        additional_tokens: 50000,
        additional_cost_usd: 0.50,
        force_unpause: true,
      });
    } finally {
      setIsAdjusting(false);
    }
  };

  return (
    <div
      data-testid="cumulative-delivery-ledger-card"
      className={`p-5 rounded-xl border transition-all ${
        is_paused
          ? 'bg-slate-900/95 border-rose-600/50 shadow-lg shadow-rose-950/20'
          : gate_verdict === 'WARNING_70'
          ? 'bg-slate-900/90 border-amber-500/40'
          : 'bg-slate-900/80 border-slate-800'
      } ${className}`}
    >
      {/* 头部：标题与硬预算门禁状态徽章 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800/80">
        <div>
          <div className="flex items-center space-x-2.5">
            <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
            <span
              data-testid="budget-gate-badge"
              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                is_paused
                  ? 'bg-rose-950/50 text-rose-300 border-rose-700/60 animate-pulse'
                  : gate_verdict === 'WARNING_70'
                  ? 'bg-amber-950/40 text-amber-300 border-amber-700/60'
                  : 'bg-emerald-950/40 text-emerald-300 border-emerald-700/60'
              }`}
            >
              {is_paused
                ? '硬预算熔断 · 保护性挂起'
                : gate_verdict === 'WARNING_70'
                ? '用量预警 (>70%)'
                : '预算充裕 · 正常推进'}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5 font-mono">
            交付编号: {delivery_id} ｜ 累计包含 {total_trials_count} 轮多智能体协作尝试
          </p>
        </div>

        {budget_tokens_limit && (
          <div className="text-right text-xs">
            <span className="text-slate-400">设定预算上限: </span>
            <span className="font-mono font-medium text-slate-200">
              {budget_tokens_limit.toLocaleString()} Tokens
            </span>
          </div>
        )}
      </div>

      {/* 4 大核心 KPI 统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 my-4">
        {/* 累计有效 Token */}
        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-1">
          <div className="text-[11px] text-slate-400">整轮累计 Token</div>
          <div className="text-base font-bold font-mono text-slate-100">
            {total_effective_tokens.toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-400 flex justify-between">
            <span>精确: {total_metered_tokens.toLocaleString()}</span>
            {total_imputed_tokens > 0 && (
              <span className="text-amber-400 font-medium">计提: +{total_imputed_tokens.toLocaleString()}</span>
            )}
          </div>
        </div>

        {/* 累计支出成本 */}
        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-1">
          <div className="text-[11px] text-slate-400">整轮总成本 ($)</div>
          <div className="text-base font-bold font-mono text-emerald-400">
            ${total_effective_cost_usd.toFixed(4)}
          </div>
          <div className="text-[10px] text-slate-400 flex justify-between">
            <span>精确: ${total_metered_cost_usd.toFixed(4)}</span>
            {total_imputed_cost_usd > 0 && (
              <span className="text-amber-400">计提: +${total_imputed_cost_usd.toFixed(4)}</span>
            )}
          </div>
        </div>

        {/* 尝试轮次与未知用量审计 */}
        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-1">
          <div className="text-[11px] text-slate-400">协作尝试 / 未知审计</div>
          <div className="text-base font-bold font-mono text-slate-100">
            {total_trials_count} 轮尝试
          </div>
          <div className="text-[10px]">
            {unmetered_trials_count > 0 ? (
              <span
                data-testid="unmetered-alert-count"
                className="text-amber-400 font-medium"
              >
                ⚠️ 包含 {unmetered_trials_count} 次未计量计提
              </span>
            ) : (
              <span className="text-emerald-400">100% 具备精确用量回执</span>
            )}
          </div>
        </div>

        {/* 预算消耗刻度 */}
        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-1">
          <div className="text-[11px] text-slate-400">预算消耗水位</div>
          <div className="text-base font-bold font-mono text-slate-100">
            {usagePercent !== null ? `${usagePercent}%` : '未设上限'}
          </div>
          <div className="w-full bg-slate-700/50 rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full transition-all ${
                is_paused
                  ? 'bg-rose-500'
                  : (usagePercent || 0) >= 70
                  ? 'bg-amber-400'
                  : 'bg-indigo-500'
              }`}
              style={{ width: `${usagePercent || 0}%` }}
            />
          </div>
        </div>
      </div>

      {/* 熔断挂起条幅与追加预算恢复交互 */}
      {is_paused && (
        <div
          data-testid="budget-fuse-alert-banner"
          className="p-3.5 rounded-lg bg-rose-950/30 border border-rose-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 my-3"
        >
          <div className="flex items-start space-x-2.5">
            <div className="w-5 h-5 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center shrink-0 mt-0.5">
              ⚠️
            </div>
            <div>
              <div className="text-xs font-semibold text-rose-200">
                协同执行已紧急暂停（Circuit Breaker Triggered）
              </div>
              <div className="text-xs text-rose-300/80 mt-0.5">
                {pause_reason || '已突破单次宏大需求硬预算门禁上限，防止失控多智能体死循环消耗。'}
              </div>
            </div>
          </div>

          {onAdjustBudget && (
            <button
              onClick={handleQuickAddBudget}
              disabled={isAdjusting || loading}
              data-testid="quick-add-budget-btn"
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-600 hover:bg-rose-500 text-white border border-rose-500/60 shadow-sm transition disabled:opacity-50 shrink-0 self-end sm:self-center"
            >
              {isAdjusting ? '追加中...' : '追加 50k Tokens 并恢复'}
            </button>
          )}
        </div>
      )}

      {/* 单次尝试账明细折叠切换 */}
      <div className="pt-2">
        <button
          onClick={() => setShowBreakdown((prev) => !prev)}
          data-testid="toggle-breakdown-btn"
          className="text-xs font-medium text-indigo-400 hover:text-indigo-300 transition flex items-center space-x-1"
        >
          <span>{showBreakdown ? '收起尝试流水明细' : '查看单次尝试流水明细 (Trial Ledger Breakdown)'}</span>
          <svg
            className={`w-3.5 h-3.5 transition-transform ${showBreakdown ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showBreakdown && (
          <div className="mt-3" data-testid="trials-breakdown-section">
            <TrialLedgerBreakdownTable trials={trials} />
          </div>
        )}
      </div>
    </div>
  );
};
