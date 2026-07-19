'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import type { KanbanTask, TaskStatus, TaskRun, TaskEvent } from '@/services/kanban';
import {
  listRuns,
  listEvents,
  listDependencies,
  listDependents,
  addComment,
  addDependency,
  removeDependency,
  getTask,
} from '@/services/kanban';
import { Clock, ExternalLink, GitBranch, Paperclip, Sparkles, User } from 'lucide-react';
import {
  NEXT_STATUSES,
  OUTCOME_STYLES,
  EVENT_KIND_STYLES,
  PRIORITY_INDICATORS,
  STATUS_DOT,
  DIAGNOSTIC_SEVERITY_STYLES,
  formatDuration,
  formatTime,
  type TaskDepInfo,
} from './kanban-styles';
import KanbanSpecifyDialog from './KanbanSpecifyDialog';
import KanbanDecomposeDialog from './KanbanDecomposeDialog';
import KanbanMarkdown from './KanbanMarkdown';
import { useAgentName } from '@/hooks/useAgentName';

function ScheduledCountdown({ until }: { until: string }) {
  const [remaining, setRemaining] = useState('');
  useEffect(() => {
    const update = () => {
      const diff = new Date(until).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining('auto-unblocking...');
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setRemaining(h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`);
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [until]);
  return (
    <span className="inline-flex items-center gap-0.5 text-[10px] text-chart-4 font-mono">
      <Clock className="w-3 h-3" /> {remaining}
    </span>
  );
}

interface KanbanTaskCardProps {
  task: KanbanTask;
  allTasks: KanbanTask[];
  onMove: (taskId: string, status: TaskStatus) => void;
  onDelete: (taskId: string) => void;
  onRefresh: () => void;
  onReclaim?: (taskId: string) => void;
  onOpenTaskDrawer?: (taskId: string) => void;
}

export default function KanbanTaskCard({
  task,
  allTasks,
  onMove,
  onDelete,
  onRefresh,
  onReclaim,
  onOpenTaskDrawer,
}: KanbanTaskCardProps) {
  const t = useTranslations('kanban');
  const agentName = useAgentName(task.agent_id);
  const [showActions, setShowActions] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [parents, setParents] = useState<TaskDepInfo[]>([]);
  const [children, setChildren] = useState<TaskDepInfo[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);
  const [showAddDep, setShowAddDep] = useState(false);
  const [addingDep, setAddingDep] = useState(false);
  const [specifyOpen, setSpecifyOpen] = useState(false);
  const [decomposeOpen, setDecomposeOpen] = useState(false);

  const toggleExpand = useCallback(async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    setDetailLoading(true);
    try {
      const [runsRes, eventsRes, depsRes, childRes] = await Promise.all([
        listRuns(task.task_id),
        listEvents(task.task_id),
        listDependencies(task.task_id),
        listDependents(task.task_id),
      ]);
      setRuns(runsRes.items);
      setEvents(eventsRes.items);

      const resolveTaskInfos = async (ids: string[]): Promise<TaskDepInfo[]> => {
        const infos: TaskDepInfo[] = [];
        for (const id of ids) {
          const local = allTasks.find((t) => t.task_id === id);
          if (local) {
            infos.push({ task_id: id, title: local.title, status: local.status });
          } else {
            try {
              const remote = await getTask(id);
              infos.push({ task_id: id, title: remote.title, status: remote.status });
            } catch {
              infos.push({ task_id: id, title: id.slice(0, 8), status: 'archived' });
            }
          }
        }
        return infos;
      };

      const [parentInfos, childInfos] = await Promise.all([
        resolveTaskInfos(depsRes.items),
        resolveTaskInfos(childRes.items),
      ]);
      setParents(parentInfos);
      setChildren(childInfos);
    } catch {
      /* silent */
    }
    setDetailLoading(false);
  }, [expanded, task.task_id, allTasks]);

  const handleRemoveDep = useCallback(
    async (parentId: string) => {
      try {
        await removeDependency(task.task_id, parentId);
        setParents((prev) => prev.filter((p) => p.task_id !== parentId));
        onRefresh();
        toast.success(t('depRemoved'));
      } catch {
        toast.error(t('depRemoveError'));
      }
    },
    [task.task_id, onRefresh, t],
  );

  const handleAddDep = useCallback(
    async (parentId: string) => {
      setAddingDep(true);
      try {
        await addDependency(task.task_id, parentId);
        const parentTask = allTasks.find((t) => t.task_id === parentId);
        if (parentTask) {
          setParents((prev) => [...prev, { task_id: parentId, title: parentTask.title, status: parentTask.status }]);
        }
        setShowAddDep(false);
        onRefresh();
        toast.success(t('depAdded'));
      } catch {
        toast.error(t('depAddError'));
      }
      setAddingDep(false);
    },
    [task.task_id, allTasks, onRefresh, t],
  );

  const handleSubmitComment = useCallback(async () => {
    if (!commentText.trim()) return;
    setSubmittingComment(true);
    try {
      const ev = await addComment(task.task_id, commentText.trim());
      setEvents((prev) => [...prev, ev]);
      setCommentText('');
    } catch {
      toast.error(t('addCommentError'));
    }
    setSubmittingComment(false);
  }, [task.task_id, commentText, t]);

  const availableParents = allTasks.filter(
    (t) => t.task_id !== task.task_id && !parents.some((p) => p.task_id === t.task_id),
  );

  const progressPill = useMemo(() => {
    if (children.length > 0) {
      const done = children.filter((c) => c.status === 'completed' || c.status === 'archived').length;
      return { done, total: children.length };
    }
    if (task.children_total > 0) {
      return { done: task.children_done, total: task.children_total };
    }
    return null;
  }, [children, task.children_total, task.children_done]);

  const relativeTime = useMemo(() => {
    const diff = Date.now() - new Date(task.created_at).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return t('justNow');
    if (minutes < 60) return t('minutesAgo', { count: minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t('hoursAgo', { count: hours });
    const days = Math.floor(hours / 24);
    return t('daysAgo', { count: days });
  }, [task.created_at, t]);

  const diagSummary = task.diagnostics_summary;

  const depStatusDot = (status: TaskStatus) => STATUS_DOT[status] ?? 'bg-muted-foreground/30';

  return (
    <div
      id={`kanban-task-${task.task_id}`}
      className="relative group rounded-full border bg-background hover:shadow transition-shadow"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className="p-2.5">
        <div className={cn('absolute left-0 top-2 bottom-2 w-0.5 rounded-full', PRIORITY_INDICATORS[task.priority])} />

        <div className="pl-2">
          <div className="flex items-start justify-between gap-1">
            <p className="text-sm font-medium leading-tight line-clamp-2 flex-1">{task.title}</p>
            <button
              onClick={toggleExpand}
              className="p-0.5 rounded hover:bg-muted shrink-0 text-muted-foreground text-xs"
              aria-label={expanded ? 'collapse' : 'expand'}
            >
              {expanded ? '\u25B2' : '\u25BC'}
            </button>
          </div>
          {task.description && <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{task.description}</p>}
          {task.status === 'running' && task.progress_note && (
            <p className="text-[10px] mt-1 text-chart-4 font-medium truncate" title={task.progress_note}>
              {task.progress_note}
            </p>
          )}

          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            {task.branch && (
              <span
                className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20 truncate max-w-[100px]"
                title={task.branch}
              >
                <GitBranch className="w-3 h-3 mr-1 shrink-0" />
                <span className="truncate">{task.branch}</span>
              </span>
            )}
            {task.agent_id && agentName && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full bg-chart-4/10 text-chart-4 border border-chart-4/20 truncate max-w-[100px]"
                title={agentName}
              >
                {agentName}
              </span>
            )}
            {task.dep_count > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {t('depBadge', { count: task.dep_count })}
              </span>
            )}
            {progressPill && (
              <span
                className={cn(
                  'text-[10px] px-1.5 py-0.5 rounded-full border',
                  progressPill.done === progressPill.total
                    ? 'bg-chart-2/10 text-chart-2 border-chart-2/20'
                    : 'bg-primary/10 text-primary border-primary/20',
                )}
              >
                {progressPill.done}/{progressPill.total}
              </span>
            )}
            {task.comment_count > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {t('commentBadge', { count: task.comment_count })}
              </span>
            )}
            {task.attachments && task.attachments.length > 0 && (
              <button
                type="button"
                data-testid={`kanban-task-attachment-badge-${task.task_id}`}
                onPointerDown={(e) => {
                  e.stopPropagation();
                }}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onOpenTaskDrawer?.(task.task_id);
                }}
                className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors cursor-pointer touch-manipulation"
                title={t('viewAttachmentsHint')}
                aria-label={t('viewAttachmentsHint')}
              >
                <Paperclip className="w-2.5 h-2.5" />
                {task.attachments.length}
              </button>
            )}
            {task.extra_skill_ids && task.extra_skill_ids.length > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-chart-3/10 text-chart-3 border border-chart-3/20 truncate max-w-[120px]">
                {task.extra_skill_ids.join(', ')}
              </span>
            )}
            {task.max_runtime_seconds != null && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-chart-5/10 text-chart-5 border border-chart-5/20">
                {t('timeoutLabel')}: {formatDuration(task.max_runtime_seconds)}
              </span>
            )}
            {task.retry_count > 0 && (
              <span className="text-[10px] text-muted-foreground">
                {t('retries')}: {task.retry_count}/{task.max_retries}
              </span>
            )}
            {task.blocked_reason && (
              <span className="inline-flex items-center gap-0.5 text-[10px] text-destructive line-clamp-1">
                {task.block_kind === 'scheduled' && <Clock className="w-3 h-3 shrink-0" />}
                {task.block_kind === 'external' && <ExternalLink className="w-3 h-3 shrink-0" />}
                {task.block_kind === 'human' && <User className="w-3 h-3 shrink-0" />}
                {task.blocked_reason}
              </span>
            )}
            {task.block_kind === 'scheduled' && task.scheduled_until && (
              <ScheduledCountdown until={task.scheduled_until} />
            )}
            {task.status === 'backlog' && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-chart-5/10 text-chart-5 border border-chart-5/20">
                <span className="w-1 h-1 rounded-full bg-chart-5 animate-pulse" />
                {t('waitingForDeps')}
              </span>
            )}
            {task.status === 'triage' && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                <span className="w-1 h-1 rounded-full bg-purple-500 animate-pulse" />
                {t('triagePending')}
              </span>
            )}
            {diagSummary && diagSummary.count > 0 && diagSummary.max_severity && (
              <span
                className={cn(
                  'inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border',
                  DIAGNOSTIC_SEVERITY_STYLES[diagSummary.max_severity]?.badge ?? 'bg-muted text-muted-foreground',
                )}
              >
                {t('diagnosticBadge', { count: diagSummary.count })}
              </span>
            )}
            <span className="text-[9px] text-muted-foreground/60 ml-auto shrink-0">{relativeTime}</span>
          </div>
          {task.attachments && task.attachments.length > 0 && (
            <p className="text-[9px] text-muted-foreground/70 mt-0.5">{t('openDetailsHint')}</p>
          )}
        </div>

        {showActions && (
          <div className="absolute top-1 right-6 flex gap-0.5">
            {task.status === 'triage' && (
              <>
                <button
                  onClick={() => setSpecifyOpen(true)}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20 transition-colors inline-flex items-center gap-0.5"
                  title={t('specifyHint')}
                >
                  <Sparkles className="w-2.5 h-2.5" />
                  {t('specify')}
                </button>
                <button
                  onClick={() => setDecomposeOpen(true)}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 transition-colors inline-flex items-center gap-0.5"
                  title={t('decomposeHint')}
                >
                  <GitBranch className="w-2.5 h-2.5" />
                  {t('decompose')}
                </button>
              </>
            )}
            {NEXT_STATUSES[task.status]?.map((ns) => (
              <button
                key={ns}
                onClick={() => onMove(task.task_id, ns)}
                className="text-[10px] px-1.5 py-0.5 rounded bg-muted hover:bg-muted-foreground/20 transition-colors"
                title={t(`moveTo.${ns}`)}
              >
                {t(`status.${ns}`)}
              </button>
            ))}
            {task.status === 'running' && onReclaim && (
              <button
                onClick={() => onReclaim(task.task_id)}
                className="text-[10px] px-1.5 py-0.5 rounded bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
                title={t('reclaimConfirm')}
              >
                {t('reclaimConfirm')}
              </button>
            )}
            <button
              onClick={() => onDelete(task.task_id)}
              className="text-[10px] px-1.5 py-0.5 rounded hover:bg-destructive/10 text-destructive/60 hover:text-destructive transition-colors"
            >
              {t('deleteAction')}
            </button>
          </div>
        )}
      </div>

      <KanbanSpecifyDialog
        task={specifyOpen ? task : null}
        open={specifyOpen}
        onOpenChange={setSpecifyOpen}
        onApplied={onRefresh}
      />
      <KanbanDecomposeDialog
        task={decomposeOpen ? task : null}
        open={decomposeOpen}
        onOpenChange={setDecomposeOpen}
        onApplied={onRefresh}
      />

      {expanded && (
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
                          className="text-[9px] text-destructive/50 hover:text-destructive opacity-0 group-hover/dep:opacity-100 transition-opacity shrink-0"
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
                        <span className="text-[9px] text-muted-foreground shrink-0">
                          ({t(`status.${child.status}`)})
                        </span>
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
                      <div key={run.run_id} className="flex items-center gap-2 text-[10px]">
                        <span
                          className={cn('font-medium', OUTCOME_STYLES[run.outcome ?? ''] ?? 'text-muted-foreground')}
                        >
                          {run.outcome ?? '...'}
                        </span>
                        <span className="text-muted-foreground">{formatDuration(run.duration_seconds)}</span>
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
                        {ev.kind === 'user_comment' && ev.payload?.body && (
                          <div className="ml-[52px] mt-0.5">
                            <KanbanMarkdown className="text-foreground/80">{String(ev.payload.body)}</KanbanMarkdown>
                          </div>
                        )}
                        {ev.kind === 'heartbeat' && ev.payload?.note && (
                          <p className="ml-[52px] text-[10px] text-chart-4/80 mt-0.5">{String(ev.payload.note)}</p>
                        )}
                        {ev.kind === 'branch_switched' && ev.payload && (
                          <p className="ml-[52px] text-[10px] text-blue-500/80 mt-0.5">
                            <span className="font-medium text-blue-500">Branch:</span>{' '}
                            {String(ev.payload.from || 'unknown')} &rarr; {String(ev.payload.to || 'unknown')}
                            {ev.payload.migrated ? ' (Migrated)' : ' (Stashed)'}
                          </p>
                        )}
                        {ev.kind === 'verification_failed' && ev.payload?.reason && (
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
                            {ev.payload.promoted_to && (
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
      )}
    </div>
  );
}
