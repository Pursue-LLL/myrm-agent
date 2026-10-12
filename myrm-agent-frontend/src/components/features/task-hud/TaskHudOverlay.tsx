/**
 * Anti-Compaction Persistent Task HUD Overlay Component.
 *
 * [INPUT] TaskHudOverlayProps (chatId, className)
 * [OUTPUT] JSX.Element - Persistent floating HUD displaying real-time task checklist and progress
 * [POS] Item 31 component. Strictly under 320 lines. Zero `any`.
 */

import React from 'react';
import {
  ListTodo,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
} from 'lucide-react';
import type { TaskHudOverlayProps, TaskStatus } from './taskHudTypes';
import { useTaskHudStore } from '@/store/useTaskHudStore';

export const TaskHudOverlay: React.FC<TaskHudOverlayProps> = ({
  chatId,
  className = '',
}) => {
  const tasks = useTaskHudStore((state) => state.tasks);
  const overallProgress = useTaskHudStore((state) => state.overallProgress);
  const isExpanded = useTaskHudStore((state) => state.isExpanded);
  const toggleExpanded = useTaskHudStore((state) => state.toggleExpanded);
  const updateTaskStatus = useTaskHudStore((state) => state.updateTaskStatus);

  if (!tasks || tasks.length === 0) {
    return null;
  }

  const completedCount = tasks.filter((t) => t.status === 'completed').length;
  const activeTask = tasks.find((t) => t.status === 'in_progress') || tasks.find((t) => t.status === 'pending');

  const getStatusIcon = (status: TaskStatus) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />;
      case 'in_progress':
        return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin shrink-0" />;
      case 'failed':
        return <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />;
      case 'pending':
      default:
        return <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />;
    }
  };

  const handleToggleTaskStatus = (taskId: string, currentStatus: TaskStatus) => {
    const nextStatus: TaskStatus = currentStatus === 'completed' ? 'pending' : 'completed';
    updateTaskStatus(taskId, nextStatus);
  };

  return (
    <section
      aria-label="抗压缩会话任务执行状态悬浮看板"
      className={`mx-3 my-2 rounded-xl border border-slate-200/90 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md shadow-sm transition-all duration-200 ${className}`}
    >
      {/* 顶部主条：当前步骤摘要与总进度条 */}
      <div className="flex items-center justify-between gap-3 p-2.5 sm:px-3.5">
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 shrink-0">
            <ListTodo className="w-4 h-4" />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
                {activeTask ? activeTask.title : '所有任务已完成'}
              </span>
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-500/20 px-1.5 py-0.2 rounded shrink-0">
                <ShieldCheck className="w-3 h-3" />
                抗压缩
              </span>
            </div>

            {/* 总体进度条 */}
            <div className="flex items-center gap-2 mt-1">
              <div className="flex-1 max-w-xs h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-blue-600 dark:bg-blue-500 transition-all duration-300 rounded-full"
                  style={{ width: `${overallProgress}%` }}
                />
              </div>
              <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400">
                {overallProgress}% ({completedCount}/{tasks.length})
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={toggleExpanded}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? '收起任务清单' : '展开任务清单'}
          className="inline-flex items-center gap-1 text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer shrink-0"
        >
          <span className="hidden sm:inline">{isExpanded ? '收起清单' : '展开任务清单'}</span>
          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {/* 展开的 Checklist 列表 */}
      {isExpanded && (
        <div className="border-t border-slate-100 dark:border-slate-800/80 p-2.5 sm:px-3.5 space-y-1.5 bg-slate-50/50 dark:bg-slate-950/30 rounded-b-xl max-h-56 overflow-y-auto">
          {tasks.map((task, index) => (
            <div
              key={task.id}
              className={`flex items-start justify-between gap-2 p-2 rounded-lg text-xs transition-colors ${
                task.status === 'in_progress'
                  ? 'bg-blue-50/80 dark:bg-blue-950/30 border border-blue-500/20'
                  : 'hover:bg-black/5 dark:hover:bg-white/5'
              }`}
            >
              <div className="flex items-start gap-2 min-w-0 flex-1">
                <button
                  type="button"
                  onClick={() => handleToggleTaskStatus(task.id, task.status)}
                  aria-label={`切换任务 ${task.title} 状态`}
                  className="mt-0.5 p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/10 transition-colors cursor-pointer"
                >
                  {getStatusIcon(task.status)}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <span className="font-mono text-[10px] text-slate-400">#{index + 1}</span>
                    <span
                      className={`font-medium ${
                        task.status === 'completed'
                          ? 'line-through text-slate-400 dark:text-slate-500'
                          : 'text-slate-800 dark:text-slate-200'
                      }`}
                    >
                      {task.title}
                    </span>
                  </div>
                  {task.details && (
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 break-words">
                      {task.details}
                    </p>
                  )}
                </div>
              </div>

              <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500 shrink-0">
                {task.progress_percent}%
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
