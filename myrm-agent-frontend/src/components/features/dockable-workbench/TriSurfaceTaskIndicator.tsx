import React from 'react';
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Clock,
  Layers,
} from 'lucide-react';
import { useDockableWorkbenchStore } from './useDockableWorkbenchStore';
import { deriveTriSurfaceState } from './dockableWorkbenchEngine';
import type { TriSurfaceMode } from './dockableWorkbenchTypes';

export interface TriSurfaceTaskIndicatorProps {
  readonly mode: TriSurfaceMode;
  readonly className?: string;
  readonly onOpenDetail?: () => void;
}

export const TriSurfaceTaskIndicator: React.FC<TriSurfaceTaskIndicatorProps> = ({
  mode,
  className = '',
  onOpenDetail,
}) => {
  const currentTask = useDockableWorkbenchStore((state) => {
    return state.currentTask;
  });

  if (!currentTask) {
    return null;
  }

  const derived = deriveTriSurfaceState(currentTask, mode);

  if (mode === 'collapsed_row') {
    return (
      <div
        data-testid="tri-surface-collapsed-row"
        className={`flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-300 ${className}`}
      >
        <div className="flex items-center gap-2">
          {currentTask.status === 'running' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
          ) : currentTask.status === 'completed' ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : currentTask.status === 'failed' ? (
            <AlertCircle className="h-3.5 w-3.5 text-rose-400" />
          ) : (
            <Activity className="h-3.5 w-3.5 text-slate-400" />
          )}
          <span className="font-medium text-slate-200">{derived.displayStatus}</span>
          <span className="text-slate-500">·</span>
          <span className="text-[11px] text-slate-400 truncate max-w-[200px]">
            {derived.currentActionSummary}
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px]">
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300">
            {derived.progressText}
          </span>
          {onOpenDetail && (
            <button
              type="button"
              onClick={onOpenDetail}
              className="text-indigo-400 hover:text-indigo-300"
            >
              详情
            </button>
          )}
        </div>
      </div>
    );
  }

  if (mode === 'expanded_card') {
    return (
      <div
        data-testid="tri-surface-expanded-card"
        className={`rounded-xl border border-slate-700/80 bg-slate-900/90 p-4 text-slate-100 shadow-md ${className}`}
      >
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-indigo-400" />
            <span className="text-xs font-semibold text-slate-200">
              任务执行看板 · {derived.displayStatus}
            </span>
          </div>
          <span className="text-xs font-mono text-indigo-300">{derived.progressText}</span>
        </div>

        <div className="my-3">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 transition-all duration-300"
              style={{ width: `${currentTask.progressPercentage}%` }}
            />
          </div>
        </div>

        <div className="rounded-lg border border-slate-800/80 bg-slate-950/50 p-2.5 text-xs">
          <p className="text-slate-300">{derived.currentActionSummary}</p>
          <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
            <span>任务标识: {currentTask.taskId}</span>
            <span>连接代次: E{currentTask.epoch}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="tri-surface-detail-drawer"
      className={`rounded-xl border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-200 ${className}`}
    >
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
        <span className="font-semibold text-indigo-400 flex items-center gap-1.5">
          <Layers className="h-3.5 w-3.5" />
          侧栏任务详情全景
        </span>
        <span className="text-[10px] font-mono text-slate-400">
          Seq #{currentTask.sequenceNo}
        </span>
      </div>

      <div className="space-y-1.5 text-[11px]">
        <div className="flex justify-between">
          <span className="text-slate-400">当前代次与步骤:</span>
          <span className="font-mono text-slate-200">{derived.progressText}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">调度执行工具:</span>
          <span className="font-mono text-indigo-300">
            {currentTask.currentTool ?? '无'}
          </span>
        </div>
        <div className="mt-2 rounded bg-slate-900 p-2 text-slate-300 font-mono text-[10px]">
          {derived.currentActionSummary}
        </div>
      </div>
    </div>
  );
};
