/**
 * [INPUT]
 * Props: totalEntries, successCount, cautionaryCount, autoTriggerActive, onRefresh, onToggleConfig
 *
 * [OUTPUT]
 * FailureRetrievalHudBar React component presenting 4-dimensional telemetry metrics.
 *
 * [POS]
 * HUD metric bar inside FailureSessionRetrievalStudioCard.
 * Strict typing applied: No `any` types allowed. Accessible buttons with focus rings. Single file < 200 lines.
 */

import React from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Zap,
  RefreshCw,
  Settings,
} from 'lucide-react';

export interface FailureRetrievalHudBarProps {
  totalEntries: number;
  successCount: number;
  cautionaryCount: number;
  autoTriggerActive: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  onToggleConfig: () => void;
}

export const FailureRetrievalHudBar: React.FC<FailureRetrievalHudBarProps> = ({
  totalEntries,
  successCount,
  cautionaryCount,
  autoTriggerActive,
  refreshing,
  onRefresh,
  onToggleConfig,
}) => {
  const successRatio =
    totalEntries > 0 ? Math.round((successCount / totalEntries) * 100) : 0;

  return (
    <aside
      aria-label="失败检索遥测指标状态栏"
      className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-muted/40 p-3 rounded-lg border border-border"
    >
      {/* 1. 总收录案例与双轨结构 */}
      <div className="flex items-center gap-3 bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="p-2 rounded bg-primary/10 text-primary">
          <ShieldAlert className="w-4 h-4" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground font-medium">双轨收录库</div>
          <div className="text-sm font-semibold tracking-tight text-foreground">
            {totalEntries} <span className="text-xs font-normal text-muted-foreground">例</span>
          </div>
        </div>
      </div>

      {/* 2. 成功解决占比 */}
      <div className="flex items-center gap-3 bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="p-2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="w-4 h-4" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground font-medium">正向解法占比</div>
          <div className="text-sm font-semibold tracking-tight text-foreground">
            {successRatio}%{' '}
            <span className="text-xs font-normal text-muted-foreground">
              ({successCount}解/{cautionaryCount}警)
            </span>
          </div>
        </div>
      </div>

      {/* 3. 避坑反模式数量 */}
      <div className="flex items-center gap-3 bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="p-2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground font-medium">避坑死胡同库</div>
          <div className="text-sm font-semibold tracking-tight text-foreground">
            {cautionaryCount}{' '}
            <span className="text-xs font-normal text-muted-foreground">条踩坑教训</span>
          </div>
        </div>
      </div>

      {/* 4. 零提示免问拦截状态与操作区 */}
      <div className="flex items-center justify-between bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded ${
              autoTriggerActive
                ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                : 'bg-muted text-muted-foreground'
            }`}
          >
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-muted-foreground font-medium">免提示拦截</div>
            <div className="text-sm font-semibold tracking-tight text-foreground">
              {autoTriggerActive ? '自动静默接管' : '已暂停'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
            title="刷新历史解法库与遥测数据"
            aria-label="刷新历史解法库"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={onToggleConfig}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            title="配置拦截器参数"
            aria-label="配置拦截器参数"
          >
            <Settings className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
};
