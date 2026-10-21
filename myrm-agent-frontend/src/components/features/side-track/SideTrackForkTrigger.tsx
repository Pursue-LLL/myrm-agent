import React from 'react';
import { GitFork, Lightbulb } from 'lucide-react';
import { useSideTrackStore } from './useSideTrackStore';
import { ReadOnlyCodeSnapshot, ReadOnlyStepSnapshot } from './sideTrackTypes';

export interface SideTrackForkTriggerProps {
  mainSessionId: string;
  mainTaskName: string;
  activeStep?: ReadOnlyStepSnapshot;
  codeSnapshots?: ReadOnlyCodeSnapshot[];
  variant?: 'compact' | 'full';
  className?: string;
}

export const SideTrackForkTrigger: React.FC<SideTrackForkTriggerProps> = ({
  mainSessionId,
  mainTaskName,
  activeStep,
  codeSnapshots = [],
  variant = 'compact',
  className = '',
}) => {
  const { openSideTrack, isDrawerOpen } = useSideTrackStore();

  const handleFork = () => {
    openSideTrack(mainSessionId, mainTaskName, activeStep, codeSnapshots);
  };

  if (variant === 'compact') {
    return (
      <button
        type="button"
        onClick={handleFork}
        aria-label="开侧边提问原理 (不打断主任务)"
        title="主任务照跑不打断，在侧边独立分支询问实现原理与架构细节"
        data-testid="side-track-fork-trigger-compact"
        className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20 hover:text-indigo-200 border border-indigo-500/30 transition-colors ${className}`}
      >
        <GitFork className="w-3 h-3 text-indigo-400" />
        <span>开侧边问原理</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={handleFork}
      aria-label="开侧边提问原理 (不打断主任务)"
      title="主任务照跑不打断，在侧边独立分支询问实现原理与架构细节"
      data-testid="side-track-fork-trigger-full"
      className={`flex items-center gap-2 p-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-850 border border-indigo-500/30 text-left transition-all group ${className}`}
    >
      <div className="p-1.5 rounded-lg bg-indigo-600/20 text-indigo-400 group-hover:bg-indigo-600/30 transition-colors">
        <Lightbulb className="w-4 h-4" />
      </div>
      <div className="flex-1 truncate">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-100">
          <span>开侧边独立解释分支</span>
          {isDrawerOpen && (
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          )}
        </div>
        <p className="text-[10px] text-zinc-400 truncate">
          主任务全速执行中 · 挂载当前瞬时代码快照 · 零上下文污染
        </p>
      </div>
      <GitFork className="w-4 h-4 text-zinc-500 group-hover:text-indigo-400 transition-colors shrink-0" />
    </button>
  );
};
