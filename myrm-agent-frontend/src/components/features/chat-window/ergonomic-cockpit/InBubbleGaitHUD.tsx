import React from 'react';
import { Activity, CheckCircle2, ChevronRight, Layers, ShieldCheck } from 'lucide-react';
import { useErgonomicCockpitStore } from './useErgonomicCockpitStore';
import type { TaskGaitProgress } from './ergonomicCockpitTypes';

interface InBubbleGaitHUDProps {
  progress?: TaskGaitProgress | null;
  className?: string;
}

export const InBubbleGaitHUD: React.FC<InBubbleGaitHUDProps> = ({
  progress: propProgress,
  className = '',
}) => {
  const { currentGait } = useErgonomicCockpitStore();
  const gait = propProgress !== undefined ? propProgress : currentGait;

  if (!gait) {
    return null;
  }

  const {
    currentStep,
    totalSteps,
    stepTitle,
    percentage,
    isDecoupledFromInput,
  } = gait;

  const isCompleted = percentage >= 100 || currentStep >= totalSteps;

  return (
    <section
      aria-label="消息顶置步态仪表视窗"
      className={`rounded-lg border border-slate-800 bg-slate-900/90 p-2.5 shadow-sm backdrop-blur transition-all ${className}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2 text-xs">
        <div className="flex items-center gap-1.5 font-medium text-slate-200">
          {isCompleted ? (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          ) : (
            <Activity className="w-3.5 h-3.5 text-sky-400 shrink-0 animate-spin" />
          )}
          <span className="truncate max-w-[280px] font-mono text-[11px]">
            {stepTitle}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {isDecoupledFromInput && (
            <span
              className="inline-flex items-center gap-1 rounded bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-mono text-indigo-300 border border-indigo-500/20"
              title="视线向心聚合：步态进度与底部输入框解耦"
            >
              <ShieldCheck className="w-2.5 h-2.5" />
              <span>Decoupled</span>
            </span>
          )}
          <span className="font-mono text-[11px] text-slate-400">
            {currentStep}/{totalSteps}
          </span>
          <span className="font-mono text-xs font-semibold text-sky-400">
            {Math.round(percentage)}%
          </span>
        </div>
      </div>

      {/* 进度条 */}
      <div className="relative w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
        <progress
          aria-label={`任务步态执行进度: ${Math.round(percentage)}%`}
          value={Math.min(100, Math.max(0, percentage))}
          max={100}
          className="sr-only"
        />
        <div
          className={`h-full transition-all duration-300 rounded-full ${
            isCompleted
              ? 'bg-emerald-500'
              : 'bg-gradient-to-r from-sky-500 to-indigo-500'
          }`}
          style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }}
        />
      </div>

      {/* 底部人体工效学微标签 */}
      <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-500">
        <div className="flex items-center gap-1">
          <Layers className="w-2.5 h-2.5" />
          <span>Foveal Centric Alignment</span>
        </div>
        <div className="flex items-center gap-0.5 text-slate-400 hover:text-slate-200 cursor-default">
          <span>In-bubble stream</span>
          <ChevronRight className="w-2.5 h-2.5" />
        </div>
      </div>
    </section>
  );
};
