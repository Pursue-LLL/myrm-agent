import React from 'react';
import type { BudgetEstimate } from './types';

interface PredictiveBudgetGaugeViewProps {
  estimate: BudgetEstimate;
  nodeCount: number;
  fanoutConcurrency: number;
  onUpdateParams: (nodes: number, concurrency: number) => void;
  onSimulateMassiveFanout: () => void;
}

export const PredictiveBudgetGaugeView: React.FC<PredictiveBudgetGaugeViewProps> = ({
  estimate,
  nodeCount,
  fanoutConcurrency,
  onUpdateParams,
  onSimulateMassiveFanout,
}) => {
  const isOverCap = estimate.is_circuit_broken;

  return (
    <section
      aria-label="前置 Token 成本预估与硬上限预算防护"
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-3 dark:border-gray-800">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            前置 Token 成本预估与硬上限预算防护
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            在多智能体扇出前静态推演算力消耗，杜绝指数级死循环与天价账单
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            data-testid="budget-guard-status-badge"
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              isOverCap
                ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300'
                : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
            }`}
          >
            {isOverCap ? '🛡️ 硬上限熔断拦截' : '✅ 预算充裕准许扇出'}
          </span>
          <button
            type="button"
            onClick={onSimulateMassiveFanout}
            className="rounded bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-300 dark:hover:bg-rose-900/50"
            data-testid="simulate-massive-fanout-btn"
          >
            模拟超限重型扇出
          </button>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Param 1: Node Count */}
        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-3 dark:border-gray-800 dark:bg-gray-800/40">
          <label htmlFor="node-count-input" className="block text-xs font-medium text-gray-500 dark:text-gray-400">
            计划 DAG 节点数
          </label>
          <div className="mt-1 flex items-center gap-2">
            <input
              id="node-count-input"
              type="number"
              min={1}
              max={64}
              value={nodeCount}
              onChange={(e) => onUpdateParams(Math.max(1, parseInt(e.target.value) || 1), fanoutConcurrency)}
              className="w-20 rounded border border-gray-300 bg-white px-2 py-1 text-sm font-semibold text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
            />
            <span className="text-xs text-gray-400">个任务单元</span>
          </div>
        </div>

        {/* Param 2: Concurrency */}
        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-3 dark:border-gray-800 dark:bg-gray-800/40">
          <label htmlFor="concurrency-input" className="block text-xs font-medium text-gray-500 dark:text-gray-400">
            计划扇出并发度
          </label>
          <div className="mt-1 flex items-center gap-2">
            <input
              id="concurrency-input"
              type="number"
              min={1}
              max={16}
              value={fanoutConcurrency}
              onChange={(e) => onUpdateParams(nodeCount, Math.max(1, parseInt(e.target.value) || 1))}
              className="w-20 rounded border border-gray-300 bg-white px-2 py-1 text-sm font-semibold text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
            />
            <span className="text-xs text-gray-400">路并发 Worker</span>
          </div>
        </div>

        {/* Predicted Tokens */}
        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-3 dark:border-gray-800 dark:bg-gray-800/40">
          <span className="block text-xs font-medium text-gray-500 dark:text-gray-400">
            预估总消耗 Token / 上限
          </span>
          <div className="mt-1 flex items-baseline gap-1">
            <span
              data-testid="predicted-tokens-val"
              className={`text-base font-bold font-mono ${
                isOverCap ? 'text-rose-600 dark:text-rose-400' : 'text-gray-900 dark:text-gray-100'
              }`}
            >
              {estimate.total_estimated_tokens.toLocaleString()}
            </span>
            <span className="text-xs text-gray-400">/ {estimate.max_tokens_cap.toLocaleString()}</span>
          </div>
        </div>

        {/* Predicted Cost */}
        <div className="rounded-md border border-gray-100 bg-gray-50/70 p-3 dark:border-gray-800 dark:bg-gray-800/40">
          <span className="block text-xs font-medium text-gray-500 dark:text-gray-400">
            预估折算金额 / 上限
          </span>
          <div className="mt-1 flex items-baseline gap-1">
            <span
              data-testid="predicted-cost-val"
              className={`text-base font-bold font-mono ${
                isOverCap ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
              }`}
            >
              ${estimate.estimated_cost_usd.toFixed(4)}
            </span>
            <span className="text-xs text-gray-400">/ ${estimate.max_cost_usd_cap.toFixed(2)}</span>
          </div>
        </div>
      </div>

      <div className="mt-3 rounded bg-gray-50 p-2.5 text-xs text-gray-700 dark:bg-gray-800/60 dark:text-gray-300">
        <strong>门禁建议: </strong>
        <span data-testid="budget-recommendation-text">{estimate.recommendation}</span>
      </div>
    </section>
  );
};
