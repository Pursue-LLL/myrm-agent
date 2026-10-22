import React from 'react';
import {
  Clock,
  Compass,
  FileCheck2,
  HelpCircle,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { useZeroTrespassStore } from './useZeroTrespassStore';

interface StepSaverQuantificationCardProps {
  className?: string;
}

export const StepSaverQuantificationCard: React.FC<StepSaverQuantificationCardProps> = ({
  className = '',
}) => {
  const { stepSaver } = useZeroTrespassStore();

  return (
    <section
      aria-label="帮你省了哪一步价值量化与诚实能力边界卡片"
      className={`rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow-sm backdrop-blur ${className}`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <TrendingUp className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">“帮你省了哪一步”价值量化</h3>
            <p className="text-[11px] text-slate-400">
              用事实说话 · 交代清楚省去步骤、权限诉求与诚实能力边界
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 rounded-full bg-indigo-500/10 px-2.5 py-1 text-xs font-mono font-medium text-indigo-300 border border-indigo-500/20">
          <Clock className="w-3.5 h-3.5" />
          <span>预计节省人工耗时: {stepSaver.estimatedMinutesSaved} 分钟</span>
        </div>
      </div>

      {/* 省去具体繁琐步骤清单 */}
      <div className="mt-4">
        <div className="text-xs font-medium text-slate-300 mb-2 flex items-center gap-1.5">
          <FileCheck2 className="w-3.5 h-3.5 text-emerald-400" />
          <span>本次任务已为您自动消除以下人工重复劳动：</span>
        </div>

        <div className="space-y-1.5">
          {stepSaver.savedSteps.map((step, idx) => (
            <div
              key={step}
              className="flex items-center gap-2 rounded-lg bg-slate-950/60 px-3 py-2 text-xs text-slate-300 border border-slate-800/80"
            >
              <span className="w-4 h-4 rounded-full bg-slate-800 text-[10px] font-mono flex items-center justify-center text-slate-400 shrink-0">
                {idx + 1}
              </span>
              <span className="truncate">{step}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 诚实能力边界声明 */}
      <div className="mt-4 rounded-lg bg-slate-950/80 border border-slate-800/90 p-3">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 mb-1">
          <Compass className="w-3.5 h-3.5 text-amber-400" />
          <span>诚实能力边界声明 (Honest Capability Boundary)</span>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          {stepSaver.honestBoundaryNotice}
        </p>
      </div>
    </section>
  );
};
