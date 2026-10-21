import React, { useState } from 'react';
import type { BudgetStatusType, ExecutionSpendState, PartialReduceReport } from './types';

interface ElasticThrottlingCardViewProps {
  spendState: ExecutionSpendState;
  reduceReport: PartialReduceReport | null;
  onSimulateStep: (statusTarget: BudgetStatusType) => void;
  onTriggerEarlyReduce: () => void;
}

const STATUS_CONFIGS: Record<
  BudgetStatusType,
  { label: string; bgBar: string; textClass: string; badgeClass: string; icon: string }
> = {
  healthy: {
    label: '健康充裕 (HEALTHY)',
    bgBar: 'bg-emerald-500',
    textClass: 'text-emerald-700 dark:text-emerald-300',
    badgeClass: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200',
    icon: '🟢',
  },
  warning: {
    label: '预警节流 (WARNING <30%)',
    bgBar: 'bg-amber-500',
    textClass: 'text-amber-700 dark:text-amber-300',
    badgeClass: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-200',
    icon: '🟡',
  },
  critical: {
    label: '危急降级 (CRITICAL <10%)',
    bgBar: 'bg-rose-500',
    textClass: 'text-rose-700 dark:text-rose-300',
    badgeClass: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-200',
    icon: '🔴',
  },
  exhausted: {
    label: '额度耗尽熔断 (EXHAUSTED)',
    bgBar: 'bg-purple-600',
    textClass: 'text-purple-700 dark:text-purple-300',
    badgeClass: 'bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-200',
    icon: '⛔',
  },
};

export const ElasticThrottlingCardView: React.FC<ElasticThrottlingCardViewProps> = ({
  spendState,
  reduceReport,
  onSimulateStep,
  onTriggerEarlyReduce,
}) => {
  const [showReportDialog, setShowReportDialog] = useState(false);
  const cfg = STATUS_CONFIGS[spendState.budget_status];
  const remainingPctDisplay = Math.round(spendState.remaining_budget_pct * 100);

  return (
    <section
      aria-label="自适应弹性扇出节流与预算耗尽优雅归约"
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-3 dark:border-gray-800">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            自适应弹性扇出节流与预算耗尽优雅归约
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            低于30%自动收紧并发、低于10%触发成果保全归约，坚决杜绝因算力耗尽全盘清零崩溃
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            data-testid="live-spend-status-badge"
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.badgeClass}`}
          >
            {cfg.icon} {cfg.label}
          </span>
          <button
            type="button"
            onClick={() => {
              onTriggerEarlyReduce();
              setShowReportDialog(true);
            }}
            className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600"
            data-testid="trigger-early-reduce-btn"
          >
            ⚡ 触发提前局部归约
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-300">
          <span>
            剩余预算水位: <strong data-testid="remaining-pct-val">{remainingPctDisplay}%</strong>
          </span>
          <span>
            已用 <strong className="font-mono">{spendState.current_tokens.toLocaleString()}</strong> Tokens /
            剩余 <strong className="font-mono">{spendState.remaining_tokens.toLocaleString()}</strong> Tokens
          </span>
        </div>
        <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
          <progress
            aria-label="剩余预算进度"
            value={Math.max(0, Math.min(100, remainingPctDisplay))}
            max={100}
            className={`h-full w-full appearance-none transition-all duration-300 [&::-webkit-progress-bar]:bg-transparent [&::-webkit-progress-value]:${cfg.bgBar} [&::-moz-progress-bar]:${cfg.bgBar}`}
          />
        </div>
      </div>

      {/* Metric Grid */}
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-2.5 dark:border-gray-800 dark:bg-gray-800/40">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">活跃扇出并发度</span>
          <span
            data-testid="active-concurrency-val"
            className="text-base font-bold font-mono text-gray-900 dark:text-gray-100"
          >
            {spendState.active_concurrency} 路
          </span>
        </div>

        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-2.5 dark:border-gray-800 dark:bg-gray-800/40">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">节流限速状态</span>
          <span
            data-testid="is-throttled-val"
            className={`text-xs font-semibold ${
              spendState.is_throttled ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'
            }`}
          >
            {spendState.is_throttled ? '⚠️ 已触发自适应降速' : '正常未限速'}
          </span>
        </div>

        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-2.5 dark:border-gray-800 dark:bg-gray-800/40">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">硬上限熔断防线</span>
          <span
            data-testid="is-circuit-broken-val"
            className={`text-xs font-semibold ${
              spendState.is_circuit_broken ? 'text-rose-600 dark:text-rose-400' : 'text-gray-600 dark:text-gray-300'
            }`}
          >
            {spendState.is_circuit_broken ? '🛑 已触发强行熔断' : '🛡️ 守卫巡航中'}
          </span>
        </div>

        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-2.5 dark:border-gray-800 dark:bg-gray-800/40">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">已发生折算费用</span>
          <span className="text-sm font-bold font-mono text-indigo-600 dark:text-indigo-400">
            ${spendState.current_cost_usd.toFixed(4)}
          </span>
        </div>
      </div>

      {/* Simulator Actions */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 dark:border-gray-800">
        <span className="text-xs text-gray-500 dark:text-gray-400">动态水位消耗模拟:</span>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => onSimulateStep('healthy')}
            className="rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-200"
            data-testid="simulate-healthy-step-btn"
          >
            80% 水位 (健康)
          </button>
          <button
            type="button"
            onClick={() => onSimulateStep('warning')}
            className="rounded bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100 dark:bg-amber-950/40 dark:text-amber-200"
            data-testid="simulate-warning-step-btn"
          >
            25% 水位 (节流)
          </button>
          <button
            type="button"
            onClick={() => onSimulateStep('critical')}
            className="rounded bg-rose-50 px-2 py-1 text-xs font-medium text-rose-800 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-200"
            data-testid="simulate-critical-step-btn"
          >
            8% 水位 (危急)
          </button>
          <button
            type="button"
            onClick={() => onSimulateStep('exhausted')}
            className="rounded bg-purple-50 px-2 py-1 text-xs font-medium text-purple-800 hover:bg-purple-100 dark:bg-purple-950/40 dark:text-purple-200"
            data-testid="simulate-exhausted-step-btn"
          >
            0% 水位 (熔断)
          </button>
        </div>
      </div>

      {/* Graceful Early Reduce Modal */}
      {showReportDialog && reduceReport && (
        <dialog
          open
          aria-label="提前局部优雅归约报告"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
        >
          <div className="w-full max-w-lg rounded-xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-800 dark:bg-gray-900">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3 dark:border-gray-800">
              <div className="flex items-center gap-2">
                <span className="text-lg">📦</span>
                <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  提前局部优雅归约交付成果 (Early Reduce Deliverable)
                </h4>
              </div>
              <button
                type="button"
                onClick={() => setShowReportDialog(false)}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
                data-testid="close-reduce-dialog-btn"
              >
                ✕
              </button>
            </div>

            <div className="mt-3 space-y-3">
              <div className="rounded bg-indigo-50/70 p-3 text-xs leading-relaxed text-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200">
                <strong>保全归约结论: </strong>
                <pre
                  data-testid="reduce-report-summary"
                  className="mt-1.5 whitespace-pre-wrap font-sans text-xs text-gray-800 dark:text-gray-200"
                >
                  {reduceReport.summary}
                </pre>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded border border-gray-100 bg-gray-50 p-2 dark:border-gray-800 dark:bg-gray-800">
                  <span className="block text-gray-500 dark:text-gray-400">已交付节点</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">
                    {reduceReport.completed_nodes.length} 个
                  </span>
                </div>
                <div className="rounded border border-gray-100 bg-gray-50 p-2 dark:border-gray-800 dark:bg-gray-800">
                  <span className="block text-gray-500 dark:text-gray-400">节省 Token</span>
                  <span className="font-bold text-indigo-600 dark:text-indigo-400">
                    {reduceReport.tokens_saved.toLocaleString()}
                  </span>
                </div>
                <div className="rounded border border-gray-100 bg-gray-50 p-2 dark:border-gray-800 dark:bg-gray-800">
                  <span className="block text-gray-500 dark:text-gray-400">交付置信度</span>
                  <span className="font-bold text-gray-900 dark:text-gray-100">
                    {Math.round(reduceReport.delivery_confidence * 100)}%
                  </span>
                </div>
              </div>

              <div className="rounded bg-gray-50 p-2 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                <strong>归约说明: </strong>
                {reduceReport.reason}
              </div>
            </div>

            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setShowReportDialog(false)}
                className="rounded bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900"
              >
                确认并接纳成果
              </button>
            </div>
          </div>
        </dialog>
      )}
    </section>
  );
};
