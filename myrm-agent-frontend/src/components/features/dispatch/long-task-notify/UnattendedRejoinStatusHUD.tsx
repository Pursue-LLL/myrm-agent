import React from 'react';
import {
  Server,
  Smartphone,
  Clock,
  RefreshCw,
  CheckCircle2,
  ChevronRight,
  ShieldCheck,
  Zap,
  ListChecks,
} from 'lucide-react';
import { useLongTaskNotifyStore } from './useLongTaskNotifyStore';
import { calculateEstimatedCompletionTime } from './longTaskRejoinEngine';

export const UnattendedRejoinStatusHUD: React.FC = () => {
  const {
    activeTask,
    isBackgrounded,
    rejoinActiveTask,
    completeTask,
    openReviewModal,
  } = useLongTaskNotifyStore();

  if (!activeTask) {
    return null;
  }

  const isRunning = activeTask.status === 'running_unattended';
  const isCompleted = activeTask.status === 'completed';

  const etaInfo = calculateEstimatedCompletionTime(
    activeTask.startedAt,
    activeTask.estimatedDurationSec
  );

  return (
    <aside
      aria-label="长任务无人值守运行态与断点重连条"
      className="w-full bg-slate-900/95 border border-emerald-500/30 rounded-xl p-3.5 text-slate-100 shadow-xl flex flex-col space-y-2.5 backdrop-blur-md transition-all"
      data-testid="unattended-rejoin-status-hud"
    >
      {/* 顶栏：运行状态、常驻环境与耗时 */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center space-x-2">
          <div className="p-1.5 rounded-md bg-emerald-600/20 text-emerald-400 border border-emerald-500/30">
            {isRunning ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            )}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-xs text-white">
                {activeTask.title}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/60 font-medium">
                {isRunning ? '无人值守持续运行中' : '长任务已完成'}
              </span>
            </div>
          </div>
        </div>

        {/* 离线切后台保活指示 */}
        <div className="flex items-center space-x-2 text-[11px] text-slate-400">
          <span className="flex items-center space-x-1 font-mono text-emerald-400">
            <Server className="w-3 h-3" />
            <span>常驻云端沙箱</span>
          </span>
          {isBackgrounded && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 font-mono">
              手机已切后台/锁屏保活
            </span>
          )}
        </div>
      </div>

      {/* 步进动态与进度条 */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <span className="truncate max-w-[280px] sm:max-w-md text-slate-300 font-sans">
            {activeTask.currentStep}
          </span>
          <span className="font-mono text-emerald-400 text-xs">
            {activeTask.progressPercent}%
          </span>
        </div>
        <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 to-indigo-500 transition-all duration-300"
            style={{ width: `${activeTask.progressPercent}%` }}
          />
        </div>
      </div>

      {/* 底栏控制条：ETA 与 重连/复盘按钮 */}
      <div className="flex items-center justify-between pt-1 border-t border-slate-800/80 text-[11px]">
        <div className="text-slate-400 flex items-center space-x-1.5 font-mono">
          <Clock className="w-3 h-3 text-slate-500" />
          <span>
            {isRunning
              ? `预计完成于 ${etaInfo.etaFormatted} (剩余 ${etaInfo.remainingSec}s)`
              : '任务执行完毕，结果可随时查验'}
          </span>
        </div>

        <div className="flex items-center space-x-2">
          {isRunning ? (
            <>
              <button
                type="button"
                onClick={rejoinActiveTask}
                aria-label="断点重连增量同步"
                className="px-2.5 py-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded border border-slate-700 transition-colors flex items-center space-x-1"
              >
                <RefreshCw className="w-3 h-3" />
                <span>重连同步</span>
              </button>
              <button
                type="button"
                onClick={completeTask}
                aria-label="模拟任务完成"
                className="px-2.5 py-1 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded transition-colors"
              >
                模拟完成
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={openReviewModal}
              aria-label="查看带来源权威清单"
              className="px-3 py-1 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded shadow flex items-center space-x-1.5 transition-all"
            >
              <ListChecks className="w-3.5 h-3.5" />
              <span>查看带来源权威清单</span>
            </button>
          )}
        </div>
      </div>
    </aside>
  );
};
