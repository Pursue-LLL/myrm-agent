'use client';

import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Layers,
  ShieldCheck,
  Sparkles,
  Target,
  XCircle,
} from 'lucide-react';

export type SubtaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped';

export interface SubtaskItemView {
  id: string;
  title: string;
  status: SubtaskStatus;
  notes?: string;
}

export interface TrapRecordView {
  fingerprint: string;
  avoidance_rule: string;
  tool_name?: string | null;
}

export interface WorkingMemoryBoardProps {
  goal?: string;
  status?: 'active' | 'interrupted' | 'completed' | 'failed';
  subtasks?: SubtaskItemView[];
  traps?: TrapRecordView[];
  digestBadge?: {
    id: string;
    completedStepsCount: number;
    ruleCount: number;
  } | null;
  className?: string;
  initiallyExpanded?: boolean;
}

export const WorkingMemoryBoard: React.FC<WorkingMemoryBoardProps> = ({
  goal,
  status = 'active',
  subtasks = [],
  traps = [],
  digestBadge = null,
  className = '',
  initiallyExpanded = true,
}) => {
  const [isExpanded, setIsExpanded] = useState(initiallyExpanded);

  if (!goal && subtasks.length === 0 && traps.length === 0 && !digestBadge) {
    return null;
  }

  const completedCount = subtasks.filter((s) => s.status === 'completed').length;
  const totalCount = subtasks.length;
  const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <div
      data-testid="working-memory-board"
      className={`rounded-xl border border-border/80 bg-card/70 backdrop-blur-md shadow-sm transition-all duration-200 overflow-hidden ${className}`}
    >
      {/* Header Bar */}
      <button
        type="button"
        data-testid="working-board-header"
        className="w-full flex items-center justify-between px-3.5 py-2.5 bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors select-none text-left"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-label={isExpanded ? '折叠手边工作台' : '展开手边工作台'}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Target className="h-3.5 w-3.5" />
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xs font-semibold text-foreground tracking-tight truncate">
              {goal || '当前长程任务目标'}
            </span>
            {totalCount > 0 && (
              <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary shrink-0">
                {completedCount}/{totalCount} ({progressPercent}%)
              </span>
            )}
            {digestBadge && (
              <span
                data-testid="digest-badge"
                className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shrink-0"
              >
                <Sparkles className="h-2.5 w-2.5" />
                已终态固化
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span
            data-testid="toggle-board-btn"
            className="text-muted-foreground hover:text-foreground transition-colors p-1"
          >
            {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </span>
        </div>
      </button>

      {/* Expandable Content */}
      {isExpanded && (
        <div className="p-3.5 space-y-3 text-xs">
          {/* Subtasks Progression */}
          {subtasks.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-muted-foreground text-[11px] font-medium">
                <Layers className="h-3 w-3" />
                <span>任务执行清单</span>
              </div>
              <div className="grid gap-1.5">
                {subtasks.map((sub) => {
                  const isCompleted = sub.status === 'completed';
                  const isInProgress = sub.status === 'in_progress';
                  const isFailed = sub.status === 'failed';

                  return (
                    <div
                      key={sub.id}
                      data-testid={`subtask-item-${sub.id}`}
                      className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 transition-colors ${
                        isCompleted
                          ? 'border-emerald-500/20 bg-emerald-500/5 text-muted-foreground'
                          : isInProgress
                            ? 'border-primary/30 bg-primary/5 text-foreground font-medium'
                            : isFailed
                              ? 'border-destructive/30 bg-destructive/5 text-destructive'
                              : 'border-border/60 bg-muted/20 text-muted-foreground'
                      }`}
                    >
                      <div className="mt-0.5 shrink-0">
                        {isCompleted ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                        ) : isInProgress ? (
                          <Clock className="h-3.5 w-3.5 text-primary animate-pulse" />
                        ) : isFailed ? (
                          <XCircle className="h-3.5 w-3.5 text-destructive" />
                        ) : (
                          <div className="h-3 w-3 rounded-full border border-muted-foreground/40 m-0.5" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1">
                          <span className={`truncate ${isCompleted ? 'line-through opacity-80' : ''}`}>
                            {sub.title}
                          </span>
                        </div>
                        {sub.notes && (
                          <p className="text-[10px] text-muted-foreground/80 mt-0.5 break-words">
                            {sub.notes}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Active Error Traps / Lessons */}
          {traps.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400 text-[11px] font-medium">
                <AlertTriangle className="h-3 w-3" />
                <span>运行时避坑防线</span>
              </div>
              <div className="grid gap-1">
                {traps.map((trap, idx) => (
                  <div
                    key={`${trap.fingerprint}-${idx}`}
                    className="flex items-start gap-2 rounded-md border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5 text-amber-800 dark:text-amber-300 text-[11px]"
                  >
                    <ShieldCheck className="h-3.5 w-3.5 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
                    <div className="flex-1 min-w-0">
                      {trap.tool_name && (
                        <span className="font-mono font-semibold mr-1.5 text-[10px] bg-amber-500/20 px-1 py-0.2 rounded">
                          {trap.tool_name}
                        </span>
                      )}
                      <span>{trap.avoidance_rule}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
