/**
 * [INPUT]
 * - ./kanban-styles::STATUS_DOT (POS: 状态圆点样式)
 * - ./KanbanMarkdown (POS: 看板安全 Markdown 渲染)
 * - @/lib/utils/a11y::REVEAL_ON_HOVER (POS: 悬停与聚焦时显现的操作按钮样式)
 *
 * [OUTPUT]
 * - DependenciesSection: 依赖与被依赖任务列表、增删依赖、跳转到相关任务
 * - CommentInputSection: 评论输入，回车发送
 * - LatestProgressSection: 最近一次运行的摘要
 *
 * [POS]
 * 任务抽屉主体里的依赖、评论、进展区段；全部受控，状态由 useKanbanTaskDrawer 提供。
 */
'use client';

import type { RefObject } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { TaskDepInfo } from './kanban-styles';
import { STATUS_DOT } from './kanban-styles';
import type { KanbanTask } from '@/services/kanban';
import KanbanMarkdown from './KanbanMarkdown';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

// --- Dependencies Section ---

interface DependenciesSectionProps {
  parents: TaskDepInfo[];
  dependents: TaskDepInfo[];
  showAddDep: boolean;
  setShowAddDep: (v: boolean) => void;
  addingDep: boolean;
  availableParents: KanbanTask[];
  progressPill: { done: number; total: number } | null;
  handleAddDep: (parentId: string) => void;
  handleRemoveDep: (parentId: string) => void;
  onNavigateTask?: (taskId: string) => void;
  t: (key: string) => string;
}

export function DependenciesSection({
  parents,
  dependents,
  showAddDep,
  setShowAddDep,
  addingDep,
  availableParents,
  progressPill,
  handleAddDep,
  handleRemoveDep,
  onNavigateTask,
  t,
}: DependenciesSectionProps) {
  return (
    <>
      <section>
        <div className="flex items-center justify-between mb-1.5">
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t('dependencies')}
          </h4>
          <button
            onClick={() => setShowAddDep(!showAddDep)}
            className="text-[10px] px-1.5 py-0.5 rounded hover:bg-primary/10 text-primary/70 hover:text-primary transition-colors"
          >
            {showAddDep ? t('cancel') : `+ ${t('addDep')}`}
          </button>
        </div>

        {parents.length === 0 && !showAddDep && (
          <p className="text-[10px] text-muted-foreground italic">{t('noDeps')}</p>
        )}

        {parents.length > 0 && (
          <div className="space-y-1">
            {parents.map((parent) => (
              <div key={parent.task_id} className="flex items-center justify-between gap-1 group">
                <button
                  onClick={() => onNavigateTask?.(parent.task_id)}
                  className="flex items-center gap-1.5 min-w-0 hover:underline decoration-muted-foreground/40"
                  disabled={!onNavigateTask}
                >
                  <span
                    className={cn(
                      'w-1.5 h-1.5 rounded-full shrink-0',
                      STATUS_DOT[parent.status] ?? 'bg-muted-foreground/30',
                    )}
                  />
                  <span className="text-[10px] text-foreground/80 truncate" title={parent.title}>
                    {parent.title}
                  </span>
                  <span className="text-[9px] text-muted-foreground shrink-0">({t(`status.${parent.status}`)})</span>
                </button>
                <button
                  onClick={() => handleRemoveDep(parent.task_id)}
                  className={cn(
                    'text-[9px] text-destructive/50 hover:text-destructive transition-opacity shrink-0',
                    REVEAL_ON_HOVER,
                  )}
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        )}

        {showAddDep && (
          <div className="mt-1 max-h-28 overflow-y-auto rounded border bg-muted/20 p-1">
            {availableParents.length === 0 ? (
              <p className="text-[10px] text-muted-foreground p-1">{t('noAvailableDeps')}</p>
            ) : (
              availableParents.map((t2) => (
                <button
                  key={t2.task_id}
                  onClick={() => handleAddDep(t2.task_id)}
                  disabled={addingDep}
                  className="w-full text-left text-[10px] px-1.5 py-1 rounded hover:bg-primary/10 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  <span
                    className={cn(
                      'w-1.5 h-1.5 rounded-full shrink-0',
                      STATUS_DOT[t2.status] ?? 'bg-muted-foreground/30',
                    )}
                  />
                  <span className="truncate">{t2.title}</span>
                  <span className="text-[9px] text-muted-foreground shrink-0 ml-auto">{t(`status.${t2.status}`)}</span>
                </button>
              ))
            )}
          </div>
        )}
      </section>

      {dependents.length > 0 && (
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
            {t('dependents')}
            {progressPill && (
              <span
                className={cn(
                  'ml-1.5 px-1 py-0.5 rounded text-[9px] font-normal',
                  progressPill.done === progressPill.total
                    ? 'bg-chart-2/20 text-chart-2'
                    : 'bg-primary/20 text-primary',
                )}
              >
                {progressPill.done}/{progressPill.total}
              </span>
            )}
          </h4>
          <div className="space-y-1">
            {dependents.map((child) => (
              <button
                key={child.task_id}
                onClick={() => onNavigateTask?.(child.task_id)}
                disabled={!onNavigateTask}
                className="flex items-center gap-1.5 min-w-0 hover:underline decoration-muted-foreground/40 w-full text-left"
              >
                <span
                  className={cn(
                    'w-1.5 h-1.5 rounded-full shrink-0',
                    STATUS_DOT[child.status] ?? 'bg-muted-foreground/30',
                  )}
                />
                <span className="text-[10px] text-foreground/80 truncate" title={child.title}>
                  {child.title}
                </span>
                <span className="text-[9px] text-muted-foreground shrink-0">({t(`status.${child.status}`)})</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

// --- Comment Input Section ---

interface CommentInputSectionProps {
  commentText: string;
  setCommentText: (v: string) => void;
  submittingComment: boolean;
  commentInputRef: RefObject<HTMLInputElement | null>;
  handleSubmitComment: () => Promise<void>;
  t: (key: string) => string;
}

export function CommentInputSection({
  commentText,
  setCommentText,
  submittingComment,
  commentInputRef,
  handleSubmitComment,
  t,
}: CommentInputSectionProps) {
  return (
    <section>
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
        {t('addComment')}
      </h4>
      <div className="flex gap-1.5">
        <input
          ref={commentInputRef}
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          onKeyDown={async (e) => {
            if (e.key === 'Enter' && !e.shiftKey && commentText.trim()) {
              e.preventDefault();
              await handleSubmitComment();
            }
          }}
          placeholder={t('commentPlaceholder')}
          className="flex-1 text-xs px-2.5 py-1.5 rounded-full border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          disabled={submittingComment}
        />
        <button
          onClick={handleSubmitComment}
          disabled={submittingComment || !commentText.trim()}
          className="text-xs px-3 py-1.5 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {t('send')}
        </button>
      </div>
    </section>
  );
}

// --- Latest Progress Section ---

interface LatestProgressSectionProps {
  latestSummary: string | null;
  t: (key: string) => string;
}

export function LatestProgressSection({ latestSummary, t }: LatestProgressSectionProps) {
  if (!latestSummary) {
    return null;
  }

  return (
    <div className="rounded-lg border bg-muted/20 px-3 py-2">
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
        {t('latestProgress')}
      </h4>
      <KanbanMarkdown className="text-foreground/80" maxLines={4}>
        {latestSummary}
      </KanbanMarkdown>
    </div>
  );
}
