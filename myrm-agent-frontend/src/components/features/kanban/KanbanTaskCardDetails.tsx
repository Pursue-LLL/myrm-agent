/**
 * [INPUT]
 * - ./useKanbanTaskCardDetails::KanbanTaskCardDetailsState (POS: 展开详情的数据与操作)
 * - ./kanban-styles (POS: 运行结果、事件类型与状态点的样式，耗时与时间格式化)
 * - ./KanbanMarkdown (POS: 评论与验收原因的安全 Markdown 渲染)
 *
 * [OUTPUT]
 * - KanbanTaskCardDetails (default): 任务卡片展开后的详情面板：依赖、被依赖、运行记录、事件时间线与评论输入
 *
 * [POS]
 * 任务卡片的展开详情视图，只渲染 `useKanbanTaskCardDetails` 交来的数据，自身不持有状态。
 */
'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { TaskStatus } from '@/services/kanban';
import { EVENT_KIND_STYLES, OUTCOME_STYLES, STATUS_DOT, formatDuration, formatTime } from './kanban-styles';
import KanbanMarkdown from './KanbanMarkdown';
import type { KanbanTaskCardDetailsState } from './useKanbanTaskCardDetails';

interface KanbanTaskCardDetailsProps {
  details: KanbanTaskCardDetailsState;
  /** 子任务进度（已完成 / 总数）；没有子任务时为 null，与卡片首屏的进度标记同源。 */
  progressPill: { done: number; total: number } | null;
}

const depStatusDot = (status: TaskStatus) => STATUS_DOT[status] ?? 'bg-muted-foreground/30';

export default function KanbanTaskCardDetails({ details, progressPill }: KanbanTaskCardDetailsProps) {
  const t = useTranslations('kanban');
  const {
    detailLoading,
    runs,
    events,
    parents,
    children,
    availableParents,
    showAddDep,
    setShowAddDep,
    addingDep,
    handleAddDep,
    handleRemoveDep,
    commentText,
    setCommentText,
    submittingComment,
    handleSubmitComment,
  } = details;

  return (
    <div className="border-t px-3 py-2 space-y-2.5">
      {detailLoading ? (
        <div className="h-12 rounded bg-muted/30 animate-pulse" />
      ) : (
        <>
          {/* Dependencies section */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <h4 className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
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
              <div className="space-y-0.5">
                {parents.map((parent) => (
                  <div key={parent.task_id} className="flex items-center justify-between gap-1 group/dep">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', depStatusDot(parent.status))} />
                      <span className="text-[10px] text-foreground/80 truncate" title={parent.title}>
                        {parent.title}
                      </span>
                      <span className="text-[9px] text-muted-foreground shrink-0">
                        ({t(`status.${parent.status}`)})
                      </span>
                    </div>
                    <button
                      onClick={() => handleRemoveDep(parent.task_id)}
                      className="text-[9px] text-destructive/50 hover:text-destructive transition-opacity shrink-0 opacity-0 group-hover/dep:opacity-100 group-focus-within/dep:opacity-100 pointer-coarse:opacity-100"
                      title={t('removeDep')}
                    >
                      &times;
                    </button>
                  </div>
                ))}
              </div>
            )}

            {showAddDep && (
              <div className="mt-1 max-h-24 overflow-y-auto rounded border bg-muted/20 p-1">
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
                      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', depStatusDot(t2.status))} />
                      <span className="truncate">{t2.title}</span>
                      <span className="text-[9px] text-muted-foreground shrink-0 ml-auto">
                        {t(`status.${t2.status}`)}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Dependents (children) section */}
          {children.length > 0 && (
            <div>
              <h4 className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
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
              <div className="space-y-0.5">
                {children.map((child) => (
                  <div key={child.task_id} className="flex items-center gap-1.5 min-w-0">
                    <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', depStatusDot(child.status))} />
                    <span className="text-[10px] text-foreground/80 truncate" title={child.title}>
                      {child.title}
                    </span>
                    <span className="text-[9px] text-muted-foreground shrink-0">({t(`status.${child.status}`)})</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Execution History */}
          <div>
            <h4 className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
              {t('executionHistory')}
            </h4>
            {runs.length === 0 ? (
              <p className="text-[10px] text-muted-foreground">{t('noRuns')}</p>
            ) : (
              <div className="space-y-1">
                {runs.map((run) => (
                  <div key={run.run_id} className="flex items-center gap-1.5 flex-wrap text-[10px]">
                    <span className={cn('font-medium', OUTCOME_STYLES[run.outcome ?? ''] ?? 'text-muted-foreground')}>
                      {run.outcome ?? '...'}
                    </span>
                    <span className="text-muted-foreground">{formatDuration(run.duration_seconds)}</span>
                    {run.token_usage?.total_tokens ? (
                      <span className="text-muted-foreground/90 font-mono text-[9px] bg-muted/60 px-1 py-0.2 rounded">
                        {(run.token_usage.total_tokens / 1000).toFixed(1)}k tok
                      </span>
                    ) : null}
                    {typeof run.cost_usd === 'number' && run.cost_usd > 0 ? (
                      <span className="text-emerald-600 dark:text-emerald-400 font-mono font-medium text-[9px] bg-emerald-500/10 px-1 py-0.2 rounded">
                        ${run.cost_usd < 0.01 ? run.cost_usd.toFixed(4) : run.cost_usd.toFixed(3)}
                      </span>
                    ) : null}
                    <span className="text-muted-foreground truncate max-w-[80px]" title={run.worker_id}>
                      {run.worker_id.slice(0, 12)}
                    </span>
                    {run.error && (
                      <span className="text-destructive truncate max-w-[100px]" title={run.error}>
                        {run.error.slice(0, 40)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Event Timeline */}
          <div>
            <h4 className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
              {t('eventTimeline')}
            </h4>
            {events.length === 0 ? (
              <p className="text-[10px] text-muted-foreground">{t('noEvents')}</p>
            ) : (
              <div className="space-y-0.5">
                {events.map((ev) => (
                  <div key={ev.event_id} className="text-[10px]">
                    <div className="flex items-center gap-1.5">
                      <span className="text-muted-foreground shrink-0">{formatTime(ev.created_at)}</span>
                      <span
                        className={cn(
                          'px-1 py-0.5 rounded text-[9px] font-medium shrink-0',
                          EVENT_KIND_STYLES[ev.kind] ?? 'bg-muted text-muted-foreground',
                        )}
                      >
                        {t(`eventKind.${ev.kind}` as Parameters<typeof t>[0])}
                      </span>
                      {ev.kind === 'user_comment' && ev.payload && (
                        <span className="text-muted-foreground italic truncate">
                          @{String(ev.payload.author ?? 'user')}
                        </span>
                      )}
                    </div>
                    {ev.kind === 'user_comment' && typeof ev.payload?.body === 'string' && (
                      <div className="ml-[52px] mt-0.5">
                        <KanbanMarkdown className="text-foreground/80">{ev.payload.body}</KanbanMarkdown>
                      </div>
                    )}
                    {ev.kind === 'heartbeat' && typeof ev.payload?.note === 'string' && (
                      <p className="ml-[52px] text-[10px] text-chart-4/80 mt-0.5">{ev.payload.note}</p>
                    )}
                    {ev.kind === 'branch_switched' && ev.payload && (
                      <p className="ml-[52px] text-[10px] text-blue-500/80 mt-0.5">
                        <span className="font-medium text-blue-500">Branch:</span>{' '}
                        {String(ev.payload.from || 'unknown')} &rarr; {String(ev.payload.to || 'unknown')}
                        {ev.payload.migrated ? ' (Migrated)' : ' (Stashed)'}
                      </p>
                    )}
                    {ev.kind === 'merge_conflict' && ev.payload && (
                      <p className="ml-[52px] text-[10px] text-destructive/80 mt-0.5">
                        {t('mergeConflictDetail', {
                          branch: String(ev.payload.branch || 'unknown'),
                        })}
                        {Array.isArray(ev.payload.conflicts) && ev.payload.conflicts.length > 0 && (
                          <>
                            {' '}
                            ·{' '}
                            {t('mergeConflictFileCount', {
                              count: ev.payload.conflicts.length,
                            })}
                          </>
                        )}
                      </p>
                    )}
                    {ev.kind === 'verification_failed' && typeof ev.payload?.reason === 'string' && (
                      <div className="ml-[52px] mt-0.5">
                        <span className="text-[10px] font-medium text-chart-5">{t('verificationReason')}:</span>
                        <KanbanMarkdown className="text-chart-5/80 mt-0.5" maxLines={4}>
                          {String(ev.payload.reason)}
                        </KanbanMarkdown>
                      </div>
                    )}
                    {ev.kind === 'specified' && ev.payload && (
                      <p className="ml-[52px] text-[10px] text-purple-600/80 dark:text-purple-400/80 mt-0.5">
                        <span className="font-medium text-purple-600 dark:text-purple-400">
                          @{String(ev.payload.author || 'specifier')}
                        </span>
                        {typeof ev.payload.promoted_to === 'string' && (
                          <span> &rarr; {t(`status.${ev.payload.promoted_to}` as Parameters<typeof t>[0])}</span>
                        )}
                        {(ev.payload.prompt_tokens != null || ev.payload.completion_tokens != null) && (
                          <span className="text-muted-foreground ml-1.5">
                            (
                            {t('tokensUsed', {
                              prompt: Number(ev.payload.prompt_tokens ?? 0),
                              completion: Number(ev.payload.completion_tokens ?? 0),
                            })}
                            )
                          </span>
                        )}
                      </p>
                    )}
                    {ev.kind === 'decomposed' && ev.payload && (
                      <p className="ml-[52px] text-[10px] text-blue-600/80 dark:text-blue-400/80 mt-0.5">
                        <span className="font-medium text-blue-600 dark:text-blue-400">
                          @{String(ev.payload.author || 'decomposer')}
                        </span>
                        <span className="ml-1">
                          {t('decomposedChildren', { count: Number(ev.payload.child_count ?? 0) })}
                        </span>
                        {(ev.payload.prompt_tokens != null || ev.payload.completion_tokens != null) && (
                          <span className="text-muted-foreground ml-1.5">
                            (
                            {t('tokensUsed', {
                              prompt: Number(ev.payload.prompt_tokens ?? 0),
                              completion: Number(ev.payload.completion_tokens ?? 0),
                            })}
                            )
                          </span>
                        )}
                      </p>
                    )}
                    {ev.kind === 'timed_out' && ev.payload && (
                      <p className="ml-[52px] text-[10px] text-chart-5/80 mt-0.5">
                        {t('timedOutDetail', {
                          elapsed: Number(ev.payload.elapsed_seconds ?? 0),
                          limit: Number(ev.payload.limit_seconds ?? 0),
                        })}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Comment input */}
          <div>
            <h4 className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
              {t('addComment')}
            </h4>
            <div className="flex gap-1">
              <input
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                onKeyDown={async (e) => {
                  if (e.key === 'Enter' && !e.shiftKey && commentText.trim()) {
                    e.preventDefault();
                    await handleSubmitComment();
                  }
                }}
                placeholder={t('commentPlaceholder')}
                className="flex-1 text-[10px] px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                disabled={submittingComment}
              />
              <button
                onClick={handleSubmitComment}
                disabled={submittingComment || !commentText.trim()}
                className="text-[10px] px-2 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {t('send')}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
