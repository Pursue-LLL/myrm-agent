/**
 * ProgressHUD.tsx
 * 桌面浮动进度抬头显示：极简胶囊状态条、实时步骤指示与展开式迷你日志抽屉
 */

import React from 'react';
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  Terminal,
  X,
} from 'lucide-react';
import {
  formatElapsedTimeString,
  formatProgressHudLabel,
} from './companionPlanHubEngine';
import { useCompanionPlanHubStore } from './useCompanionPlanHubStore';

export interface ProgressHUDProps {
  className?: string;
  onOpenMainWindow?: () => void;
  onStop?: () => void;
}

export const ProgressHUD: React.FC<ProgressHUDProps> = ({
  className = '',
  onOpenMainWindow,
  onStop,
}) => {
  const displayMode = useCompanionPlanHubStore((state) => state.displayMode);
  const executionProgress = useCompanionPlanHubStore(
    (state) => state.executionProgress
  );
  const isProgressLogsExpanded = useCompanionPlanHubStore(
    (state) => state.isProgressLogsExpanded
  );
  const toggleProgressLogsExpanded = useCompanionPlanHubStore(
    (state) => state.toggleProgressLogsExpanded
  );
  const setDisplayMode = useCompanionPlanHubStore(
    (state) => state.setDisplayMode
  );

  if (displayMode !== 'progress_hud' || executionProgress === null) {
    return null;
  }

  const { currentStepIndex, totalSteps, currentStepTitle, elapsedSeconds, logs } =
    executionProgress;

  const percent = Math.min(
    100,
    Math.round((currentStepIndex / Math.max(1, totalSteps)) * 100)
  );
  const hudLabel = formatProgressHudLabel(
    currentStepIndex,
    totalSteps,
    currentStepTitle
  );
  const timeStr = formatElapsedTimeString(elapsedSeconds);

  const handleStop = (): void => {
    setDisplayMode('pet_only');
    if (onStop !== undefined) {
      onStop();
    }
  };

  return (
    <section
      data-testid="companion-progress-hud"
      aria-label="伴侣常驻任务进度抬头显示"
      className={`flex flex-col items-center gap-1.5 z-50 select-none ${className}`}
    >
      {/* 极简浮动胶囊条 */}
      <div
        data-testid="progress-hud-capsule"
        className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/95 backdrop-blur-md border border-slate-700/80 shadow-xl text-xs text-slate-200"
      >
        <Activity className="w-3.5 h-3.5 text-emerald-400 animate-spin shrink-0" />

        {/* 步骤标签文字 */}
        <span
          data-testid="progress-hud-label"
          className="font-medium text-[11px] truncate max-w-[200px]"
        >
          {hudLabel}
        </span>

        {/* 耗时与百分比 */}
        <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-400">
          <Clock className="w-3 h-3 text-slate-400" />
          <span>{timeStr}</span>
          <span className="text-slate-500">|</span>
          <span>{percent}%</span>
        </span>

        {/* 展开/收起日志抽屉按钮 */}
        <button
          type="button"
          data-testid="toggle-hud-logs-btn"
          aria-label={isProgressLogsExpanded ? '收起步骤日志' : '展开步骤日志'}
          onClick={() => toggleProgressLogsExpanded()}
          className="p-1 rounded-full text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
        >
          {isProgressLogsExpanded ? (
            <ChevronUp className="w-3.5 h-3.5" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
        </button>

        {/* 呼出主窗口 */}
        {onOpenMainWindow !== undefined && (
          <button
            type="button"
            data-testid="hud-open-main-btn"
            aria-label="展开主工作台"
            onClick={onOpenMainWindow}
            className="p-1 rounded-full text-slate-400 hover:text-blue-400 hover:bg-slate-800 transition-colors"
            title="查看完整主工作台"
          >
            <ExternalLink className="w-3 h-3" />
          </button>
        )}

        {/* 叫停按钮 */}
        <button
          type="button"
          data-testid="hud-stop-btn"
          aria-label="叫停当前任务"
          onClick={handleStop}
          className="p-1 rounded-full text-slate-400 hover:text-red-400 hover:bg-slate-800 transition-colors"
          title="叫停"
        >
          <X className="w-3 h-3" />
        </button>
      </div>

      {/* 迷你步骤日志抽屉 */}
      {isProgressLogsExpanded && (
        <div
          data-testid="hud-logs-drawer"
          className="w-80 max-h-40 bg-slate-950/95 backdrop-blur-md border border-slate-800 rounded-xl p-2.5 shadow-2xl flex flex-col gap-1.5 overflow-hidden animate-in fade-in slide-in-from-top-1"
        >
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-400 border-b border-slate-800 pb-1">
            <Terminal className="w-3 h-3 text-emerald-400" />
            <span>执行步骤实时流</span>
          </div>
          <div
            data-testid="hud-logs-list"
            className="flex-1 overflow-y-auto font-mono text-[10px] text-slate-300 flex flex-col gap-1"
          >
            {logs.length === 0 ? (
              <span className="text-slate-500">正在建立任务执行上下文...</span>
            ) : (
              logs.map((log, index) => (
                <div key={index} className="truncate">
                  {log}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </section>
  );
};
