'use client';

/**
 * [INPUT] @/services/milestones::Milestone (POS: 里程碑数据契约), @/lib/utils/a11y (POS: 悬停显现与键盘激活)
 * [OUTPUT] MilestoneRow: 单条里程碑行（完成勾选、双击内联重命名、展开详情与任务进度）
 * [POS] ProjectMilestonePanel 的列表行，完成、删除与重命名都通过回调交给面板处理。
 */

import { useEffect, useRef, useState } from 'react';
import { Check, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { type Milestone } from '@/services/milestones';
import { activateOnKey, REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export function MilestoneRow({
  milestone,
  progress,
  onComplete,
  onDelete,
  onRename,
}: {
  milestone: Milestone;
  progress?: { milestoneId: string; totalTasks: number; completedTasks: number; progress: number };
  onComplete: (ms: Milestone) => void;
  onDelete: (ms: Milestone) => void;
  onRename: (ms: Milestone, newTitle: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(milestone.title);
  const editRef = useRef<HTMLInputElement>(null);
  const hasDetails = milestone.description || milestone.acceptanceCriteria;
  const hasTasks = progress && progress.totalTasks > 0;

  useEffect(() => {
    if (editing) {
      editRef.current?.focus();
    }
  }, [editing]);

  const commitRename = () => {
    const trimmed = editValue.trim();
    setEditing(false);
    if (trimmed && trimmed !== milestone.title) {
      onRename(milestone, trimmed);
    } else {
      setEditValue(milestone.title);
    }
  };

  return (
    <div>
      <div className="group flex items-center gap-1 text-[10px] text-foreground/80">
        <button
          onClick={() => onComplete(milestone)}
          className={cn(
            'w-3 h-3 rounded-sm border border-muted-foreground/30 flex items-center justify-center shrink-0',
            'hover:border-primary/60 hover:bg-primary/10 transition-colors',
          )}
        >
          {milestone.status === 'completed' && <Check size={8} className="text-primary" />}
        </button>
        <div className="flex-1 min-w-0">
          {editing ? (
            <input
              ref={editRef}
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  commitRename();
                }
                if (e.key === 'Escape') {
                  setEditing(false);
                  setEditValue(milestone.title);
                }
              }}
              className="w-full h-4 px-0.5 text-[10px] rounded border border-primary/30 bg-transparent outline-none"
            />
          ) : (
            // oxlint-disable-next-line jsx-a11y/no-static-element-interactions -- dynamic role is not resolvable by static analysis
            <span
              className={cn('truncate block', hasDetails ? 'cursor-pointer hover:text-primary/80' : 'cursor-text')}
              onClick={() => hasDetails && setOpen(!open)}
              role={hasDetails ? 'button' : undefined}
              tabIndex={hasDetails ? 0 : undefined}
              onKeyDown={activateOnKey}
              onDoubleClick={() => {
                setEditValue(milestone.title);
                setEditing(true);
              }}
            >
              {milestone.title}
            </span>
          )}
          {hasTasks && (
            <div className="flex items-center gap-1 mt-px">
              <div className="flex-1 h-[3px] rounded-full bg-muted-foreground/10 overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary/70 transition-all duration-300"
                  style={{ width: `${progress.progress}%` }}
                />
              </div>
              <span className="text-[8px] text-muted-foreground/50 shrink-0">
                {progress.completedTasks}/{progress.totalTasks}
              </span>
            </div>
          )}
        </div>
        <button
          onClick={() => onDelete(milestone)}
          className={cn('transition-opacity text-muted-foreground/40 hover:text-destructive-text', REVEAL_ON_HOVER)}
        >
          <Trash2 size={8} />
        </button>
      </div>
      {open && hasDetails && (
        <div className="ml-4 mt-0.5 text-[9px] text-muted-foreground/60 space-y-0.5">
          {milestone.description && <p className="line-clamp-2">{milestone.description}</p>}
          {milestone.acceptanceCriteria && <p className="line-clamp-1 italic">{milestone.acceptanceCriteria}</p>}
        </div>
      )}
    </div>
  );
}
