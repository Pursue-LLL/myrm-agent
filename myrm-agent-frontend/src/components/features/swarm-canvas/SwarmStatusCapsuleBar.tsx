/**
 * SwarmStatusCapsuleBar.tsx
 * 多智能体状态总览胶囊：实时攻坚进度、并发状态分布与状态筛选过滤
 */

import React, { useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Filter,
  Layers,
  Sparkles,
} from 'lucide-react';
import type { SwarmWorkerStatus } from './swarmCanvasTypes';
import {
  calculateSwarmSummaryStats,
  formatSwarmStatusCapsuleLabel,
} from './swarmCanvasEngine';
import { useSwarmCanvasStore } from './useSwarmCanvasStore';

export interface SwarmStatusCapsuleBarProps {
  className?: string;
  onFilterChange?: (filter: SwarmWorkerStatus | 'all') => void;
}

export const SwarmStatusCapsuleBar: React.FC<SwarmStatusCapsuleBarProps> = ({
  className = '',
  onFilterChange,
}) => {
  const workers = useSwarmCanvasStore((state) => state.workers);
  const statusFilter = useSwarmCanvasStore((state) => state.statusFilter);
  const setStatusFilter = useSwarmCanvasStore((state) => state.setStatusFilter);

  const stats = useMemo(() => {
    return calculateSwarmSummaryStats(workers);
  }, [workers]);

  const capsuleLabel = useMemo(() => {
    return formatSwarmStatusCapsuleLabel(stats);
  }, [stats]);

  const handleSelectFilter = (filter: SwarmWorkerStatus | 'all'): void => {
    setStatusFilter(filter);
    if (onFilterChange !== undefined) {
      onFilterChange(filter);
    }
  };

  return (
    <header
      data-testid="swarm-status-capsule-bar"
      aria-label="多智能体集群状态总览"
      className={`flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-2xl shadow-lg select-none text-slate-200 ${className}`}
    >
      {/* 左侧集群统计胶囊 */}
      <div className="flex items-center gap-2.5">
        <div className="relative flex items-center justify-center">
          <div className="w-8 h-8 rounded-full bg-blue-950/80 border border-blue-700/60 flex items-center justify-center">
            <Layers className="w-4 h-4 text-blue-400" />
          </div>
          {stats.running > 0 && (
            <span
              data-testid="swarm-running-pulse-dot"
              className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-500 rounded-full animate-ping"
            />
          )}
        </div>

        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-100">
              智能体军团协同看板
            </span>
            <span
              data-testid="swarm-progress-badge"
              className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-emerald-400 font-mono font-semibold"
            >
              总进度 {stats.progressPercent}%
            </span>
          </div>
          <span
            data-testid="swarm-status-text"
            className="text-[11px] text-slate-400 mt-0.5"
          >
            {capsuleLabel}
          </span>
        </div>
      </div>

      {/* 右侧状态过滤芯片选择器 */}
      <div className="flex items-center gap-1.5 text-xs">
        <span className="text-slate-500 text-[11px] flex items-center gap-1 mr-1">
          <Filter className="w-3 h-3" />
          <span>过滤:</span>
        </span>

        <button
          type="button"
          data-testid="filter-all-btn"
          aria-pressed={statusFilter === 'all'}
          onClick={() => handleSelectFilter('all')}
          className={`px-2.5 py-1 rounded-lg transition-colors ${
            statusFilter === 'all'
              ? 'bg-blue-600 text-white font-semibold'
              : 'text-slate-400 hover:text-slate-200 bg-slate-950/60'
          }`}
        >
          全部 ({stats.total})
        </button>

        {stats.running > 0 && (
          <button
            type="button"
            data-testid="filter-running-btn"
            aria-pressed={statusFilter === 'running'}
            onClick={() => handleSelectFilter('running')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
              statusFilter === 'running'
                ? 'bg-emerald-600 text-white font-semibold'
                : 'text-emerald-400 hover:bg-emerald-950/40 bg-slate-950/60'
            }`}
          >
            <Activity className="w-3 h-3 animate-spin" />
            <span>执行中 ({stats.running})</span>
          </button>
        )}

        {stats.waitingApproval > 0 && (
          <button
            type="button"
            data-testid="filter-approval-btn"
            aria-pressed={statusFilter === 'waiting_approval'}
            onClick={() => handleSelectFilter('waiting_approval')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
              statusFilter === 'waiting_approval'
                ? 'bg-amber-600 text-white font-semibold'
                : 'text-amber-400 hover:bg-amber-950/40 bg-slate-950/60'
            }`}
          >
            <AlertTriangle className="w-3 h-3 animate-bounce" />
            <span>待授权 ({stats.waitingApproval})</span>
          </button>
        )}

        {stats.completed > 0 && (
          <button
            type="button"
            data-testid="filter-completed-btn"
            aria-pressed={statusFilter === 'completed'}
            onClick={() => handleSelectFilter('completed')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
              statusFilter === 'completed'
                ? 'bg-blue-600 text-white font-semibold'
                : 'text-slate-400 hover:bg-slate-800 bg-slate-950/60'
            }`}
          >
            <CheckCircle2 className="w-3 h-3 text-blue-400" />
            <span>达成 ({stats.completed})</span>
          </button>
        )}
      </div>
    </header>
  );
};
