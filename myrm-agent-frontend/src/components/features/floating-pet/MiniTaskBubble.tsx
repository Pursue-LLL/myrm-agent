import React from 'react';
import {
  X,
  ExternalLink,
  Activity,
  CheckCircle2,
  AlertCircle,
  Clock,
} from 'lucide-react';
import { useFloatingPetStore } from './useFloatingPetStore';
import { PetTaskItem } from './floatingPetTypes';

export interface MiniTaskBubbleProps {
  onOpenMainWindow?: (taskId: string) => void;
  className?: string;
}

export const MiniTaskBubble: React.FC<MiniTaskBubbleProps> = ({
  onOpenMainWindow,
  className = '',
}) => {
  const {
    activeTask,
    isBubbleExpanded,
    toggleBubbleExpanded,
    clearActiveTask,
  } = useFloatingPetStore();

  if (!isBubbleExpanded || !activeTask) {
    return null;
  }

  const handleOpenMain = () => {
    if (onOpenMainWindow) {
      onOpenMainWindow(activeTask.id);
    }
  };

  const renderStatusBadge = (task: PetTaskItem) => {
    if (task.status === 'completed') {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
          <CheckCircle2 className="w-3 h-3" />
          已完成 (100%)
        </span>
      );
    }
    if (task.status === 'failed') {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-400 bg-red-500/10 px-2 py-0.5 rounded border border-red-500/20">
          <AlertCircle className="w-3 h-3" />
          执行遇阻
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20 animate-pulse">
        <Activity className="w-3 h-3" />
        执行中 {task.progress}%
      </span>
    );
  };

  return (
    <div
      data-testid="mini-task-bubble"
      className={`absolute right-16 top-0 z-50 w-72 rounded-xl bg-zinc-900/98 backdrop-blur-md border border-zinc-750 p-3.5 shadow-2xl transition-all duration-200 ${className}`}
    >
      {/* 头部状态与关闭按钮 */}
      <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-xs font-bold text-zinc-100">后台伴随任务</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              toggleBubbleExpanded(false);
            }}
            title="收起气泡"
            aria-label="收起气泡"
            className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 任务主体内容 */}
      <div className="my-2.5 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <h4 className="text-xs font-semibold text-zinc-200 line-clamp-2 leading-relaxed">
            {activeTask.title}
          </h4>
          {renderStatusBadge(activeTask)}
        </div>

        {/* 进度条 */}
        <div className="w-full bg-zinc-950 rounded-full h-1.5 overflow-hidden border border-zinc-800">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              activeTask.status === 'completed'
                ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]'
                : 'bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.8)]'
            }`}
            style={{ width: `${activeTask.progress}%` }}
          />
        </div>

        <p className="text-[11px] text-zinc-400 leading-normal line-clamp-3 font-mono bg-zinc-950/60 p-2 rounded-lg border border-zinc-850">
          {activeTask.summary}
        </p>
      </div>

      {/* 底部操作条 */}
      <div className="flex items-center justify-between pt-2 border-t border-zinc-800 text-xs">
        <button
          type="button"
          onClick={() => {
            clearActiveTask();
          }}
          className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          归档清除
        </button>

        <button
          type="button"
          onClick={handleOpenMain}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-600/30 transition-colors"
        >
          <span>查看工件详情</span>
          <ExternalLink className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};
