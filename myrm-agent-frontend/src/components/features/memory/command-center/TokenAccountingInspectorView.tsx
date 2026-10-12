/**
 * [INPUT]
 * Props: budgetConfig, accounting, onUpdateBudget, onSimulate, simulating
 *
 * [OUTPUT]
 * TokenAccountingInspectorView: Dual-track token accounting and knapsack tuner for Item 122.
 *
 * [POS]
 * Command-center subview for token cost economics and knapsack tuning knobs.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 260 lines.
 */

import React, { useState } from 'react';
import {
  Coins,
  Sliders,
  Play,
  RotateCcw,
  ShieldAlert,
  Percent,
} from 'lucide-react';
import type {
  BilledTokenBudgetDTO,
  TokenAccountingReportDTO,
} from '@/services/memory/budgetPacking';
import { FALLBACK_BUDGET } from './budgetPackingFallbacks';

export interface TokenAccountingInspectorViewProps {
  budgetConfig: BilledTokenBudgetDTO;
  accounting: TokenAccountingReportDTO;
  onUpdateBudget: (newBudget: BilledTokenBudgetDTO) => void;
  onSimulate: (budget: BilledTokenBudgetDTO) => void;
  simulating: boolean;
}

export const TokenAccountingInspectorView: React.FC<TokenAccountingInspectorViewProps> = ({
  budgetConfig,
  accounting,
  onUpdateBudget,
  onSimulate,
  simulating,
}) => {
  const [maxTokens, setMaxTokens] = useState<number>(budgetConfig.max_billed_tokens);
  const [lambda, setLambda] = useState<number>(budgetConfig.diversity_penalty_lambda);
  const [redundancyCeil, setRedundancyCeil] = useState<number>(
    budgetConfig.max_redundancy_threshold,
  );
  const [backfill, setBackfill] = useState<boolean>(budgetConfig.allow_greedy_backfill);

  const handleApplyAndSimulate = () => {
    const updated: BilledTokenBudgetDTO = {
      ...budgetConfig,
      max_billed_tokens: maxTokens,
      diversity_penalty_lambda: lambda,
      max_redundancy_threshold: redundancyCeil,
      allow_greedy_backfill: backfill,
    };
    onUpdateBudget(updated);
    onSimulate(updated);
  };

  const handleReset = () => {
    setMaxTokens(FALLBACK_BUDGET.max_billed_tokens);
    setLambda(FALLBACK_BUDGET.diversity_penalty_lambda);
    setRedundancyCeil(FALLBACK_BUDGET.max_redundancy_threshold);
    setBackfill(FALLBACK_BUDGET.allow_greedy_backfill);
    onUpdateBudget(FALLBACK_BUDGET);
    onSimulate(FALLBACK_BUDGET);
  };

  return (
    <div className="space-y-4">
      {/* 头部原理说明 */}
      <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 space-y-1.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
          <Coins className="w-4 h-4 shrink-0" />
          <span>双轨 Token 计量哲学：计费 Token ≠ 存储 Token</span>
        </div>
        <p className="text-xs text-emerald-800 dark:text-emerald-300/90 leading-relaxed">
          <strong>计费 Token (Billed Tokens)</strong> 直接拼装入提示词向大模型发起调用，产生账单；
          <strong>存储 Token (Storage Tokens)</strong> 驻留在 SQLite 或向量索引中供系统内部检索，不产生调用费用。
          贪心装箱算法致力于在严格锁死计费 Token 的前提下，最大化召回有用信息量。
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧：双轨 Token 计量大盘 */}
        <div className="p-4 bg-card/60 rounded-lg border border-border space-y-3.5">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between border-b border-border/60 pb-2">
            <span>双轨 Token 成本与效益审计报告</span>
            <span className="font-mono text-[11px] text-primary">
              审查样本: {accounting.total_candidates_examined} 条
            </span>
          </div>

          <div className="space-y-3 pt-1">
            {/* 计费 Token 进度 */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground flex items-center gap-1.5">
                  <Percent className="w-3.5 h-3.5 text-blue-500" />
                  <span>计费 Token 预算消费 (Billed Tokens)</span>
                </span>
                <span className="font-mono font-medium text-foreground">
                  {accounting.billed_tokens_spent} / {accounting.billed_tokens_budget}t ({accounting.budget_utilization_pct}%)
                </span>
              </div>
              <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all"
                  style={{ width: `${Math.min(100, accounting.budget_utilization_pct)}%` }}
                />
              </div>
            </div>

            {/* 存储 Token 节省对比 */}
            <div className="p-3 rounded-lg bg-muted/20 border border-border/80 space-y-2">
              <div className="text-xs font-medium text-foreground">存储 Token 过滤与节省</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-muted-foreground text-[11px]">总索引存储体积:</span>
                  <div className="font-mono font-semibold text-foreground">
                    {accounting.storage_tokens_total} Tokens
                  </div>
                </div>
                <div>
                  <span className="text-muted-foreground text-[11px]">离线节省体积:</span>
                  <div className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                    {accounting.storage_tokens_saved} Tokens
                  </div>
                </div>
              </div>
            </div>

            {/* 冗余过滤审计 */}
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 space-y-1 text-xs">
              <div className="font-medium text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>拦截的冗余语义 Token 数量: {accounting.redundant_tokens_filtered} Tokens</span>
              </div>
              <p className="text-[11px] text-amber-800 dark:text-amber-300/90 leading-relaxed">
                这些冗余片段在传统固定 limit 模式下会被盲目塞入模型，造成模型注意力分散与调用费浪费。
              </p>
            </div>
          </div>
        </div>

        {/* 右侧：装箱参数调节与仿真演练 */}
        <div className="p-4 bg-card/60 rounded-lg border border-border space-y-3.5">
          <div className="flex items-center justify-between border-b border-border/60 pb-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <Sliders className="w-4 h-4 text-primary" />
              <span>贪心背包调优控制台</span>
            </div>
            <button
              type="button"
              aria-label="恢复默认配置"
              onClick={handleReset}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary rounded p-1"
            >
              <RotateCcw className="w-3 h-3" />
              <span>恢复默认</span>
            </button>
          </div>

          <div className="space-y-3 text-xs">
            {/* 旋钮 1：max_billed_tokens */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label htmlFor="input-max-billed-tokens" className="font-medium text-foreground">
                  计费 Token 硬预算上限 (Max Billed Tokens)
                </label>
                <span className="font-mono font-semibold text-primary">{maxTokens}t</span>
              </div>
              <input
                id="input-max-billed-tokens"
                type="range"
                min={50}
                max={500}
                step={10}
                value={maxTokens}
                onChange={(e) => setMaxTokens(Number(e.target.value))}
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            {/* 旋钮 2：diversity_penalty_lambda */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label htmlFor="input-diversity-penalty-lambda" className="font-medium text-foreground">
                  多样性惩罚权重 λ (Diversity Penalty)
                </label>
                <span className="font-mono font-semibold text-purple-600 dark:text-purple-400">
                  {lambda.toFixed(2)}
                </span>
              </div>
              <input
                id="input-diversity-penalty-lambda"
                type="range"
                min={0.1}
                max={1.0}
                step={0.05}
                value={lambda}
                onChange={(e) => setLambda(Number(e.target.value))}
                className="w-full accent-purple-500 cursor-pointer"
              />
            </div>

            {/* 旋钮 3：max_redundancy_threshold */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label htmlFor="input-max-redundancy-threshold" className="font-medium text-foreground">
                  语义重叠淘汰上限 (Max Redundancy Ceiling)
                </label>
                <span className="font-mono font-semibold text-amber-600 dark:text-amber-400">
                  {(redundancyCeil * 100).toFixed(0)}%
                </span>
              </div>
              <input
                id="input-max-redundancy-threshold"
                type="range"
                min={0.2}
                max={0.8}
                step={0.05}
                value={redundancyCeil}
                onChange={(e) => setRedundancyCeil(Number(e.target.value))}
                className="w-full accent-amber-500 cursor-pointer"
              />
            </div>

            {/* 开关：allow_greedy_backfill */}
            <div className="flex items-center justify-between pt-1">
              <label htmlFor="checkbox-greedy-backfill" className="font-medium text-foreground cursor-pointer">
                开启贪心背包填缝优化 (Allow Greedy Backfill)
              </label>
              <input
                id="checkbox-greedy-backfill"
                type="checkbox"
                checked={backfill}
                onChange={(e) => setBackfill(e.target.checked)}
                className="rounded accent-primary w-4 h-4 cursor-pointer focus:ring-2 focus:ring-primary"
              />
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                aria-label="执行双轨装箱模拟计算"
                onClick={handleApplyAndSimulate}
                disabled={simulating}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              >
                <Play className={`w-3.5 h-3.5 ${simulating ? 'animate-spin' : ''}`} />
                <span>{simulating ? '模拟装箱中...' : '应用并执行装箱模拟'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
