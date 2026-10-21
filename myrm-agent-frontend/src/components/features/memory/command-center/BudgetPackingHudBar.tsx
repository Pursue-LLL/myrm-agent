/**
 * [INPUT]
 * Props: accounting, refreshing, onRefresh, onReset
 *
 * [OUTPUT]
 * BudgetPackingHudBar: 4-metric telemetry HUD bar for Item 122.
 *
 * [POS]
 * Telemetry HUD header component in BudgetGreedyPackingStudioCard.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 160 lines.
 */

import React from 'react';
import {
  Percent,
  TrendingUp,
  Layers,
  FilterX,
  RefreshCw,
  RotateCcw,
} from 'lucide-react';
import type { TokenAccountingReportDTO } from '@/services/memory/budgetPacking';

export interface BudgetPackingHudBarProps {
  accounting: TokenAccountingReportDTO;
  refreshing: boolean;
  onRefresh: () => void;
  onReset: () => void;
}

export const BudgetPackingHudBar: React.FC<BudgetPackingHudBarProps> = ({
  accounting,
  refreshing,
  onRefresh,
  onReset,
}) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-muted/40 rounded-lg border border-border">
      {/* 指标 1：预算填满率 */}
      <div className="flex items-center gap-2.5 p-2 rounded bg-card/60 border border-border/80">
        <div className="p-1.5 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400">
          <Percent className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] text-muted-foreground font-medium">
            预算填满率 (Billed Tokens)
          </div>
          <div className="text-sm font-semibold text-foreground flex items-center gap-1">
            <span>{accounting.budget_utilization_pct}%</span>
            <span className="text-[10px] text-muted-foreground font-normal font-mono">
              ({accounting.billed_tokens_spent}/{accounting.billed_tokens_budget})
            </span>
          </div>
        </div>
      </div>

      {/* 指标 2：平均边际价值密度 */}
      <div className="flex items-center gap-2.5 p-2 rounded bg-card/60 border border-border/80">
        <div className="p-1.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <TrendingUp className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] text-muted-foreground font-medium">
            平均边际价值密度 (MVD)
          </div>
          <div className="text-sm font-semibold text-foreground flex items-center gap-1 font-mono">
            <span>{accounting.average_marginal_density.toFixed(4)}</span>
            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-normal">
              高密度装箱
            </span>
          </div>
        </div>
      </div>

      {/* 指标 3：存储 Token 节省 */}
      <div className="flex items-center gap-2.5 p-2 rounded bg-card/60 border border-border/80">
        <div className="p-1.5 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400">
          <Layers className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] text-muted-foreground font-medium">
            存储 Token 离线节省
          </div>
          <div className="text-sm font-semibold text-foreground flex items-center gap-1 font-mono">
            <span>{accounting.storage_tokens_saved}</span>
            <span className="text-[10px] text-purple-600 dark:text-purple-400 font-normal">
              Tokens 省除
            </span>
          </div>
        </div>
      </div>

      {/* 指标 4：语义冗余拦截与操作 */}
      <div className="flex items-center justify-between p-2 rounded bg-card/60 border border-border/80">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <FilterX className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[11px] text-muted-foreground font-medium">
              语义冗余拦截
            </div>
            <div className="text-sm font-semibold text-foreground flex items-center gap-1 font-mono">
              <span>{accounting.redundant_tokens_filtered}</span>
              <span className="text-[10px] text-amber-600 dark:text-amber-400 font-normal">
                Tokens 抑制
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="刷新装箱遥测数据"
            onClick={onRefresh}
            disabled={refreshing}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
            title="刷新装箱遥测数据"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            aria-label="恢复推荐预算配置"
            onClick={onReset}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            title="恢复推荐预算配置"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
