import React from 'react';
import { AdjustBudgetPayload, WorkflowBurnStatus } from './types';
import { BudgetTierAlertBanner } from './BudgetTierAlertBanner';

export interface TokenBurnRateHUDProps {
  status: WorkflowBurnStatus;
  onAdjustBudget?: (payload: AdjustBudgetPayload) => void;
  className?: string;
}

export const TokenBurnRateHUD: React.FC<TokenBurnRateHUDProps> = ({
  status,
  onAdjustBudget,
  className = '',
}) => {
  const { verdict } = status;
  const pct = Math.min(100, Math.max(0, verdict.used_pct));

  // Determine progress bar color based on tier
  const progressColor =
    verdict.tier === 'TIER3_SUSPENDED'
      ? 'bg-red-500'
      : verdict.tier === 'TIER2_DEGRADED'
      ? 'bg-amber-500'
      : verdict.tier === 'TIER1_NOTICE'
      ? 'bg-yellow-500'
      : 'bg-emerald-500';

  // Sort agent burn entries in descending order
  const agentEntries = Object.entries(status.agent_burn_distribution).sort(
    ([, a], [, b]) => b - a
  );
  const maxAgentTokens = agentEntries.length > 0 ? agentEntries[0][1] : 1;

  return (
    <div
      className={`bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 shadow-sm space-y-5 text-gray-800 dark:text-gray-200 ${className}`}
      data-testid="token-burn-rate-hud"
    >
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">🔥</span>
          <div>
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
              海量 Agent 编排 Token 燃速全景 HUD
            </h3>
            <p className="text-[11px] text-gray-400">
              工作流: <span className="font-mono">{status.workflow_id}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-orange-100 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300 flex items-center gap-1.5 border border-orange-200 dark:border-orange-800/60">
            <span className="h-2 w-2 rounded-full bg-orange-500 animate-pulse" />
            <span>{status.active_agent_count} 个并发 Agent 运行中</span>
          </span>
        </div>
      </div>

      {/* Tier Alert Banner (Conditional) */}
      <BudgetTierAlertBanner verdict={verdict} onAdjustBudget={onAdjustBudget} />

      {/* Metrics Stat Cards */}
      <div className="grid grid-cols-3 gap-3">
        {/* Instant Burn Rate */}
        <div className="p-3.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">瞬时燃烧速率</div>
          <div className="text-lg font-extrabold text-orange-600 dark:text-orange-400 mt-1">
            {status.tokens_per_sec.toLocaleString()}{' '}
            <span className="text-xs font-normal text-gray-500">Tokens/s</span>
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            折合每小时: <span className="font-medium">${status.cost_per_hour_usd.toFixed(2)}</span>
          </div>
        </div>

        {/* Total Tokens Cumulative */}
        <div className="p-3.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">累计消耗 Token</div>
          <div className="text-lg font-extrabold text-gray-900 dark:text-gray-100 mt-1">
            {status.total_cumulative_tokens.toLocaleString()}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5 flex gap-2">
            <span>P: {status.cumulative_prompt_tokens.toLocaleString()}</span>
            <span>C: {status.cumulative_completion_tokens.toLocaleString()}</span>
          </div>
        </div>

        {/* Cumulative Cost & Budget */}
        <div className="p-3.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">已花金额 / 预设预算</div>
          <div className="text-lg font-extrabold text-blue-600 dark:text-blue-400 mt-1">
            ${status.cumulative_cost_usd.toFixed(2)}
            {status.budget_cost_usd ? (
              <span className="text-xs font-normal text-gray-500"> / ${status.budget_cost_usd.toFixed(2)}</span>
            ) : null}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            预算 Token: {status.budget_tokens ? status.budget_tokens.toLocaleString() : '不限'}
          </div>
        </div>
      </div>

      {/* Tiered Budget Safety Ladder Gauge */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between text-xs font-medium">
          <span className="text-gray-700 dark:text-gray-300">多阶段阶梯式风控进度</span>
          <span className="font-mono text-gray-500">
            {pct.toFixed(1)}% ({verdict.tier})
          </span>
        </div>

        {/* Relative Bar with 50%, 80%, 100% tick marks */}
        <div className="relative h-3 w-full bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${progressColor}`}
            style={{ width: `${pct}%` }}
            data-testid="budget-ladder-progress-bar"
          />

          {/* Tick lines */}
          <div className="absolute top-0 bottom-0 left-[50%] w-[1.5px] bg-yellow-600/40 z-10" />
          <div className="absolute top-0 bottom-0 left-[80%] w-[1.5px] bg-amber-600/60 z-10" />
        </div>

        <div className="flex justify-between text-[10px] text-gray-400 pt-0.5">
          <span>0%</span>
          <span className="text-yellow-600 dark:text-yellow-400 font-medium">50% 关注</span>
          <span className="text-amber-600 dark:text-amber-400 font-medium">80% 降级</span>
          <span className="text-red-600 dark:text-red-400 font-medium">100% 挂起</span>
        </div>
      </div>

      {/* Concurrent Agents Burn Heatmap / Distribution */}
      {agentEntries.length > 0 && (
        <div className="space-y-2.5 pt-2 border-t border-gray-100 dark:border-gray-800">
          <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300">
            <span>活跃子 Agent 燃速热力分布 (Top Consumers)</span>
            <span className="text-[10px] text-gray-400">共 {agentEntries.length} 个子任务</span>
          </div>

          <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
            {agentEntries.slice(0, 5).map(([agentName, tokens]) => {
              const agentRatio = (tokens / maxAgentTokens) * 100;
              return (
                <div key={agentName} className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="font-mono truncate max-w-[200px] text-gray-600 dark:text-gray-400">
                      {agentName}
                    </span>
                    <span className="font-semibold text-gray-700 dark:text-gray-300">
                      {tokens.toLocaleString()} Tokens
                    </span>
                  </div>
                  <div className="h-1.5 w-full bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-orange-400 dark:bg-orange-500 rounded-full transition-all"
                      style={{ width: `${agentRatio}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
