/**
 * ElasticSwarmCanvas.tsx
 * 自适应弹性多智能体网格画布：动态网格弹性排版，彻底根除卡片重叠遮挡与点击失效
 */

import React, { useMemo } from 'react';
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock,
  Sparkles,
  Wrench,
} from 'lucide-react';
import type { SwarmWorkerItem } from './swarmCanvasTypes';
import {
  deriveAdaptiveGridColumns,
  filterWorkersByStatus,
  formatWorkerStatusBadge,
} from './swarmCanvasEngine';
import { useSwarmCanvasStore } from './useSwarmCanvasStore';

export interface ElasticSwarmCanvasProps {
  className?: string;
  onWorkerClick?: (worker: SwarmWorkerItem) => void;
}

export const ElasticSwarmCanvas: React.FC<ElasticSwarmCanvasProps> = ({
  className = '',
  onWorkerClick,
}) => {
  const workers = useSwarmCanvasStore((state) => state.workers);
  const statusFilter = useSwarmCanvasStore((state) => state.statusFilter);
  const focusWorker = useSwarmCanvasStore((state) => state.focusWorker);

  const displayedWorkers = useMemo(() => {
    return filterWorkersByStatus(workers, statusFilter);
  }, [workers, statusFilter]);

  const gridColumnsClass = useMemo(() => {
    return deriveAdaptiveGridColumns(displayedWorkers.length);
  }, [displayedWorkers.length]);

  const handleCardClick = (worker: SwarmWorkerItem): void => {
    focusWorker(worker.id);
    if (onWorkerClick !== undefined) {
      onWorkerClick(worker);
    }
  };

  if (displayedWorkers.length === 0) {
    return (
      <section
        data-testid="elastic-swarm-canvas-empty"
        aria-label="智能体网格画布空状态"
        className={`flex flex-col items-center justify-center p-12 bg-slate-900/60 rounded-2xl border border-slate-800 text-slate-500 text-xs ${className}`}
      >
        <Bot className="w-8 h-8 text-slate-600 mb-2" />
        <span>暂无匹配此状态过滤条件的协同智能体</span>
      </section>
    );
  }

  return (
    <section
      data-testid="elastic-swarm-canvas"
      aria-label="多智能体弹性网格画布"
      className={`w-full overflow-hidden ${className}`}
    >
      <div
        data-testid="swarm-grid-container"
        className={`grid gap-3.5 ${gridColumnsClass}`}
      >
        {displayedWorkers.map((worker) => {
          const badgeMeta = formatWorkerStatusBadge(worker.status);
          const lastLog =
            worker.thinkingLogs.length > 0
              ? worker.thinkingLogs[worker.thinkingLogs.length - 1]
              : '就绪';

          return (
            <button
              key={worker.id}
              type="button"
              data-testid={`worker-card-${worker.id}`}
              onClick={() => handleCardClick(worker)}
              aria-label={`查看智能体 ${worker.name} 的执行轨迹`}
              className="relative group flex flex-col p-3.5 bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-2xl shadow-md text-left transition-all hover:scale-[1.01] hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500/40 select-none overflow-hidden"
              style={{
                boxShadow: `inset 0 0 12px 1px ${badgeMeta.haloColor}`,
              }}
            >
              {/* 顶部身份与状态徽章 */}
              <div className="flex items-center justify-between w-full border-b border-slate-800/80 pb-2">
                <div className="flex items-center gap-2">
                  <div
                    className="w-7 h-7 rounded-full flex items-center justify-center border"
                    style={{
                      backgroundColor: `${worker.colorTheme}15`,
                      borderColor: worker.colorTheme,
                    }}
                  >
                    <Bot
                      className="w-3.5 h-3.5"
                      style={{ color: worker.colorTheme }}
                    />
                  </div>

                  <div className="flex flex-col">
                    <span className="text-xs font-bold text-slate-100 truncate max-w-[130px]">
                      {worker.name}
                    </span>
                    <span className="text-[10px] text-slate-400 truncate max-w-[130px]">
                      {worker.role}
                    </span>
                  </div>
                </div>

                <span
                  data-testid={`worker-status-badge-${worker.id}`}
                  className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${badgeMeta.badgeBg} ${badgeMeta.badgeText}`}
                >
                  {badgeMeta.label}
                </span>
              </div>

              {/* 当前步骤任务标题 */}
              <div className="my-2.5 flex flex-col gap-1 w-full">
                <span className="text-[11px] font-medium text-slate-200 line-clamp-2 leading-relaxed">
                  {worker.currentTaskTitle}
                </span>

                {/* 最新思维流小切片 */}
                <div className="text-[10px] text-slate-400 font-mono flex items-center gap-1 truncate bg-slate-950/60 px-2 py-1 rounded-md border border-slate-850">
                  <Sparkles className="w-3 h-3 text-amber-400 shrink-0" />
                  <span className="truncate">{lastLog}</span>
                </div>
              </div>

              {/* 进度百分比条 */}
              <div className="w-full flex flex-col gap-1 mt-auto pt-1">
                <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span className="flex items-center gap-1">
                    <Wrench className="w-3 h-3 text-slate-500" />
                    <span>{worker.toolCalls.length} 工具调用</span>
                  </span>
                  <span className="text-emerald-400 font-bold">
                    {worker.progressPercent}%
                  </span>
                </div>

                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 transition-all duration-300 rounded-full"
                    style={{ width: `${worker.progressPercent}%` }}
                  />
                </div>
              </div>

              {/* 悬停卡片时的透镜唤起微提示 */}
              <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800/90 rounded-full p-1 text-slate-300">
                <ChevronRight className="w-3.5 h-3.5" />
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
};
