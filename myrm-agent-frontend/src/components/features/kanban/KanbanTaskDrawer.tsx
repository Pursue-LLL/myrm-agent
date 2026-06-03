'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/primitives/sheet';
import type { KanbanTask, TaskStatus, TaskRun, TaskEvent, TaskDiagnostic, PromoteResult } from '@/services/kanban';
import {
  listRuns,
  listEvents,
  listDependencies,
  listDependents,
  addComment,
  addDependency,
  removeDependency,
  getTask,
  moveTask,
  promoteTask,
  reclaimTask,
  updateTask,
  getTaskDiagnostics,
} from '@/services/kanban';
import {
  NEXT_STATUSES,
  PRIORITY_STYLES,
  STATUS_DOT,
  TIMEOUT_PRESETS,
  formatDate,
  formatDuration,
  type TaskDepInfo,
} from './kanban-styles';
import { KanbanRunHistory, KanbanEventTimeline } from './KanbanEventTimeline';
import KanbanDiagnosticsSection from './KanbanDiagnosticsSection';
import KanbanMarkdown from './KanbanMarkdown';
import { Clock, ExternalLink, Paperclip, X, FileText, User } from 'lucide-react';
import { useAgentName } from '@/hooks/useAgentName';
import useAgentStore from '@/store/useAgentStore';
import { getApiUrl } from '@/lib/api';

interface KanbanTaskDrawerProps {
  task: KanbanTask | null;
  allTasks: KanbanTask[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRefresh: () => void;
  onNavigateTask?: (taskId: string) => void;
}

export default function KanbanTaskDrawer({
  task,
  allTasks,
  open,
  onOpenChange,
  onRefresh,
  onNavigateTask,
}: KanbanTaskDrawerProps) {
  const t = useTranslations('kanban');
  const agentName = useAgentName(task?.agent_id);
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [parents, setParents] = useState<TaskDepInfo[]>([]);
  const [children, setChildren] = useState<TaskDepInfo[]>([]);
  const [diagnostics, setDiagnostics] = useState<TaskDiagnostic[]>([]);
  const [loading, setLoading] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);
  const [showAddDep, setShowAddDep] = useState(false);
  const [addingDep, setAddingDep] = useState(false);
  const [editingCriteria, setEditingCriteria] = useState(false);
  const [criteriaText, setCriteriaText] = useState('');
  const [savingCriteria, setSavingCriteria] = useState(false);
  const [editingSkills, setEditingSkills] = useState(false);
  const [skillsText, setSkillsText] = useState('');
  const [editingTimeout, setEditingTimeout] = useState(false);
  const [timeoutValue, setTimeoutValue] = useState<number | null>(null);
  const [promoteConfirm, setPromoteConfirm] = useState<PromoteResult | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [showReclaimDialog, setShowReclaimDialog] = useState(false);
  const [reclaimReason, setReclaimReason] = useState('');
  const [reclaimAgentId, setReclaimAgentId] = useState('');
  const [reclaiming, setReclaiming] = useState(false);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const allTasksRef = useRef(allTasks);
  allTasksRef.current = allTasks;
  const commentInputRef = useRef<HTMLInputElement>(null);
  const attachInputRef = useRef<HTMLInputElement>(null);

  const loadDetails = useCallback(async (taskId: string) => {
    setLoading(true);
    try {
      const [runsRes, eventsRes, depsRes, childRes, diagRes] = await Promise.all([
        listRuns(taskId),
        listEvents(taskId),
        listDependencies(taskId),
        listDependents(taskId),
        getTaskDiagnostics(taskId),
      ]);
      setRuns(runsRes.items);
      setEvents(eventsRes.items);
      setDiagnostics(diagRes.diagnostics);

      const currentTasks = allTasksRef.current;
      const resolveInfos = async (ids: string[]): Promise<TaskDepInfo[]> => {
        const infos: TaskDepInfo[] = [];
        for (const id of ids) {
          const local = currentTasks.find((tk) => tk.task_id === id);
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

      const [parentInfos, childInfos] = await Promise.all([resolveInfos(depsRes.items), resolveInfos(childRes.items)]);
      setParents(parentInfos);
      setChildren(childInfos);
    } catch {
      /* silent */
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (open && task) {
      loadDetails(task.task_id);
      fetchAgents();
      setCommentText('');
      setShowAddDep(false);
      setEditingCriteria(false);
      setEditingTimeout(false);
    } else {
      setRuns([]);
      setEvents([]);
      setParents([]);
      setChildren([]);
      setDiagnostics([]);
    }
  }, [open, task, loadDetails, fetchAgents]);

  useEffect(() => {
    if (!open || !task) return;
    const taskId = task.task_id;
    const onEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail as { task_id?: string } | undefined;
      if (detail?.task_id === taskId) {
        loadDetails(taskId);
      }
    };
    window.addEventListener('kanban-task-updated', onEvent);
    return () => window.removeEventListener('kanban-task-updated', onEvent);
  }, [open, task, loadDetails]);

  const handleMove = useCallback(
    async (targetStatus: TaskStatus) => {
      if (!task) return;
      if (task.status === 'backlog' && targetStatus === 'ready') {
        setPromoting(true);
        try {
          const result = await promoteTask(task.task_id, false);
          if (result.promoted) {
            onRefresh();
            onOpenChange(false);
            toast.success(t('promoteSuccess'));
          } else {
            setPromoteConfirm(result);
          }
        } catch {
          toast.error(t('promoteError'));
        }
        setPromoting(false);
        return;
      }
      try {
        await moveTask(task.task_id, targetStatus);
        onRefresh();
        onOpenChange(false);
      } catch {
        toast.error(t('moveError'));
      }
    },
    [task, onRefresh, onOpenChange, t],
  );

  const handleForcePromote = useCallback(async () => {
    if (!task) return;
    setPromoting(true);
    try {
      const result = await promoteTask(task.task_id, true);
      if (result.promoted) {
        setPromoteConfirm(null);
        onRefresh();
        onOpenChange(false);
        toast.success(t('promoteSuccess'));
      }
    } catch {
      toast.error(t('promoteError'));
    }
    setPromoting(false);
  }, [task, onRefresh, onOpenChange, t]);

  const handleReclaim = useCallback(async () => {
    if (!task) return;
    setReclaiming(true);
    try {
      const result = await reclaimTask(task.task_id, reclaimReason || undefined, reclaimAgentId || undefined);
      if (result.reclaimed) {
        setShowReclaimDialog(false);
        setReclaimReason('');
        setReclaimAgentId('');
        onRefresh();
        toast.success(t('reclaimSuccess'));
      }
    } catch {
      toast.error(t('reclaimFailed'));
    }
    setReclaiming(false);
  }, [task, reclaimReason, reclaimAgentId, onRefresh, t]);

  const handleRemoveDep = useCallback(
    async (parentId: string) => {
      if (!task) return;
      try {
        await removeDependency(task.task_id, parentId);
        setParents((prev) => prev.filter((p) => p.task_id !== parentId));
        onRefresh();
        toast.success(t('depRemoved'));
      } catch {
        toast.error(t('depRemoveError'));
      }
    },
    [task, onRefresh, t],
  );

  const handleAddDep = useCallback(
    async (parentId: string) => {
      if (!task) return;
      setAddingDep(true);
      try {
        await addDependency(task.task_id, parentId);
        const parentTask = allTasksRef.current.find((tk) => tk.task_id === parentId);
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
    [task, onRefresh, t],
  );

  const handleAttachUpload = useCallback(
    async (files: File[]) => {
      if (!task || files.length === 0) return;
      const existingCount = task.attachment_ids?.length ?? 0;
      const remaining = 10 - existingCount;
      if (remaining <= 0) {
        toast.warning(t('attachmentLimitExceeded'));
        return;
      }
      const toUpload = files.slice(0, remaining);
      if (toUpload.length < files.length) {
        toast.warning(t('attachmentLimitExceeded'));
      }
      setUploadingAttachment(true);
      try {
        const results = await Promise.allSettled(
          toUpload.map(async (file) => {
            const formData = new FormData();
            formData.append('file', file);
            const resp = await fetch(getApiUrl('/files/upload'), { method: 'POST', body: formData });
            if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
            const data = await resp.json();
            return data.file_id as string;
          }),
        );
        const newIds = results
          .filter((r): r is PromiseFulfilledResult<string> => r.status === 'fulfilled')
          .map((r) => r.value);
        const failedCount = results.filter((r) => r.status === 'rejected').length;
        if (failedCount > 0) {
          toast.error(t('attachmentUploadError'));
        }
        if (newIds.length > 0) {
          const existingIds = task.attachment_ids ?? [];
          await updateTask(task.task_id, { attachment_ids: [...existingIds, ...newIds] });
          onRefresh();
          toast.success(t('attachmentAdded'));
        }
      } catch {
        toast.error(t('attachmentUploadError'));
      }
      setUploadingAttachment(false);
    },
    [task, onRefresh, t],
  );

  const handleRemoveAttachment = useCallback(
    async (fileId: string) => {
      if (!task) return;
      const updated = (task.attachment_ids ?? []).filter((id) => id !== fileId);
      try {
        await updateTask(task.task_id, { attachment_ids: updated });
        onRefresh();
        toast.success(t('attachmentRemoved'));
      } catch {
        toast.error(t('attachmentRemoveError'));
      }
    },
    [task, onRefresh, t],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const files = Array.from(e.dataTransfer.files);
      handleAttachUpload(files);
    },
    [handleAttachUpload],
  );

  const handlePaste = useCallback(
    (e: ClipboardEvent) => {
      const items = Array.from(e.clipboardData?.items ?? []);
      const files = items
        .filter((item) => item.kind === 'file')
        .map((item) => item.getAsFile())
        .filter((f): f is File => f !== null);
      if (files.length > 0) {
        e.preventDefault();
        handleAttachUpload(files);
      }
    },
    [handleAttachUpload],
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, [open, handlePaste]);

  const handleSubmitComment = useCallback(async () => {
    if (!task || !commentText.trim()) return;
    setSubmittingComment(true);
    try {
      const ev = await addComment(task.task_id, commentText.trim());
      setEvents((prev) => [...prev, ev]);
      setCommentText('');
    } catch {
      toast.error(t('addCommentError'));
    }
    setSubmittingComment(false);
  }, [task, commentText, t]);

  const handleSaveCriteria = useCallback(async () => {
    if (!task) return;
    setSavingCriteria(true);
    try {
      await updateTask(task.task_id, {
        completion_criteria: criteriaText.trim(),
      });
      setEditingCriteria(false);
      onRefresh();
      toast.success(t('criteriaUpdated'));
    } catch {
      toast.error(t('criteriaUpdateError'));
    }
    setSavingCriteria(false);
  }, [task, criteriaText, onRefresh, t]);

  const handleSaveSkills = useCallback(async () => {
    if (!task) return;
    try {
      const parsed = skillsText
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      await updateTask(task.task_id, { extra_skill_ids: parsed });
      setEditingSkills(false);
      onRefresh();
      toast.success(t('skillsUpdated'));
    } catch {
      toast.error(t('skillsUpdateError'));
    }
  }, [task, skillsText, onRefresh, t]);

  const handleSaveTimeout = useCallback(
    async (value: number | null) => {
      if (!task) return;
      try {
        await updateTask(task.task_id, { max_runtime_seconds: value });
        setEditingTimeout(false);
        onRefresh();
        toast.success(t('timeoutUpdated'));
      } catch {
        toast.error(t('timeoutUpdateError'));
      }
    },
    [task, onRefresh, t],
  );

  const handleAgentChange = useCallback(
    async (agentId: string | null) => {
      if (!task) return;
      try {
        await updateTask(task.task_id, { agent_id: agentId });
        onRefresh();
      } catch {
        toast.error(t('updateError'));
      }
    },
    [task, onRefresh, t],
  );

  const latestSummary = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i--) {
      if (runs[i].summary) return runs[i].summary;
    }
    return null;
  }, [runs]);

  const progressPill = useMemo(() => {
    if (children.length > 0) {
      const done = children.filter((c) => c.status === 'completed' || c.status === 'archived').length;
      return { done, total: children.length };
    }
    if (task && task.children_total > 0) {
      return { done: task.children_done, total: task.children_total };
    }
    return null;
  }, [children, task]);

  const assignedAgent = useMemo(
    () => (task?.agent_id ? (agents.find((a) => a.id === task.agent_id) ?? null) : null),
    [task?.agent_id, agents],
  );

  const availableParents = useMemo(
    () =>
      task
        ? allTasks.filter((tk) => tk.task_id !== task.task_id && !parents.some((p) => p.task_id === tk.task_id))
        : [],
    [task, allTasks, parents],
  );

  if (!task) return null;

  const nextStatuses = NEXT_STATUSES[task.status] ?? [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[400px] sm:max-w-[440px] overflow-y-auto p-0" hideCloseButton>
        <div className="sticky top-0 z-10 bg-background border-b px-4 py-3">
          <SheetHeader>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={cn(
                    'w-2.5 h-2.5 rounded-full shrink-0',
                    STATUS_DOT[task.status] ?? 'bg-muted-foreground/30',
                  )}
                />
                <SheetTitle className="text-sm truncate">{task.title}</SheetTitle>
              </div>
              <button
                onClick={() => onOpenChange(false)}
                className="p-1 rounded-full hover:bg-muted transition-colors shrink-0 text-muted-foreground text-sm"
              >
                &times;
              </button>
            </div>
            <SheetDescription className="sr-only">{t('taskDetails')}</SheetDescription>
          </SheetHeader>

          {/* Status actions */}
          {(nextStatuses.length > 0 || task.status === 'running') && (
            <div className="flex gap-1.5 mt-2 flex-wrap">
              {nextStatuses.map((ns) => (
                <button
                  key={ns}
                  onClick={() => handleMove(ns)}
                  disabled={promoting}
                  className="text-[10px] px-2 py-1 rounded-full bg-muted hover:bg-muted-foreground/20 transition-colors font-medium disabled:opacity-50"
                >
                  {t(`moveTo.${ns}`)}
                </button>
              ))}
              {task.status === 'running' && (
                <button
                  onClick={() => setShowReclaimDialog(true)}
                  className="text-[10px] px-2 py-1 rounded-full bg-destructive/10 hover:bg-destructive/20 text-destructive font-medium transition-colors"
                >
                  {t('reclaimConfirm')}
                </button>
              )}
            </div>
          )}

          {/* Reclaim confirmation dialog */}
          {showReclaimDialog && (
            <div className="mt-2 p-2.5 rounded-lg border border-destructive/30 bg-destructive/5 space-y-2">
              <p className="text-[11px] font-medium text-destructive">{t('reclaimTitle')}</p>
              <p className="text-[10px] text-muted-foreground">{t('reclaimDesc')}</p>
              <input
                type="text"
                value={reclaimReason}
                onChange={(e) => setReclaimReason(e.target.value)}
                placeholder={t('reclaimReasonPlaceholder')}
                className="w-full text-[10px] px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-destructive/50"
              />
              {agents.length > 0 && (
                <div className="space-y-1">
                  <label className="text-[10px] text-muted-foreground">{t('reclaimReassignLabel')}</label>
                  <select
                    value={reclaimAgentId}
                    onChange={(e) => setReclaimAgentId(e.target.value)}
                    className="w-full text-[10px] px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-destructive/50"
                  >
                    <option value="">—</option>
                    {agents.map((ag) => (
                      <option key={ag.id} value={ag.id}>
                        {ag.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="flex gap-2 pt-1">
                <button
                  onClick={handleReclaim}
                  disabled={reclaiming}
                  className="text-[10px] px-2.5 py-1 rounded-full bg-destructive/20 hover:bg-destructive/30 text-destructive font-medium disabled:opacity-50"
                >
                  {t('reclaimConfirm')}
                </button>
                <button
                  onClick={() => {
                    setShowReclaimDialog(false);
                    setReclaimReason('');
                    setReclaimAgentId('');
                  }}
                  className="text-[10px] px-2.5 py-1 rounded-full bg-muted hover:bg-muted-foreground/20 font-medium"
                >
                  {t('cancel')}
                </button>
              </div>
            </div>
          )}

          {/* Promote confirmation dialog */}
          {promoteConfirm && (
            <div className="mt-2 p-2.5 rounded-lg border border-chart-5/30 bg-chart-5/5 space-y-2">
              <p className="text-[11px] font-medium text-chart-5">{t('promoteUnmetDeps')}</p>
              <ul className="space-y-1">
                {promoteConfirm.unmet_parents.map((p) => (
                  <li key={p.task_id} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span
                      className={cn('w-1.5 h-1.5 rounded-full', STATUS_DOT[p.status] ?? 'bg-muted-foreground/30')}
                    />
                    <span className="truncate">{p.title}</span>
                    <span className="text-[9px] opacity-60">({p.status})</span>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2 pt-1">
                <button
                  onClick={handleForcePromote}
                  disabled={promoting}
                  className="text-[10px] px-2.5 py-1 rounded-full bg-chart-5/20 hover:bg-chart-5/30 text-chart-5 font-medium disabled:opacity-50"
                >
                  {t('promoteForce')}
                </button>
                <button
                  onClick={() => setPromoteConfirm(null)}
                  className="text-[10px] px-2.5 py-1 rounded-full bg-muted hover:bg-muted-foreground/20 font-medium"
                >
                  {t('cancel')}
                </button>
              </div>
            </div>
          )}
        </div>

        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-lg bg-muted/30 animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="p-4 space-y-4">
            {/* Basic info */}
            <div className="space-y-1.5">
              {task.description && (
                <KanbanMarkdown className="text-muted-foreground">{task.description}</KanbanMarkdown>
              )}
              <div className="flex items-center gap-2 flex-wrap text-[10px]">
                <span className={cn('px-1.5 py-0.5 rounded-full border font-medium', PRIORITY_STYLES[task.priority])}>
                  {task.priority}
                </span>
                <span className="text-muted-foreground">{t(`status.${task.status}`)}</span>
                {task.agent_id && agentName && (
                  <span
                    className="px-1.5 py-0.5 rounded-full bg-chart-4/10 text-chart-4 border border-chart-4/20 truncate max-w-[120px]"
                    title={agentName}
                  >
                    {agentName}
                  </span>
                )}
                {progressPill && (
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded-full border',
                      progressPill.done === progressPill.total
                        ? 'bg-chart-2/10 text-chart-2 border-chart-2/20'
                        : 'bg-primary/10 text-primary border-primary/20',
                    )}
                  >
                    {progressPill.done}/{progressPill.total}
                  </span>
                )}
              </div>
              <div className="flex gap-3 text-[10px] text-muted-foreground/70 mt-1">
                <span>
                  {t('createdAt')}: {formatDate(task.created_at)}
                </span>
                <span>
                  {t('updatedAt')}: {formatDate(task.updated_at)}
                </span>
              </div>
              {editingTimeout ? (
                <div className="mt-1 rounded border border-chart-5/30 bg-chart-5/5 px-2 py-1.5 space-y-1">
                  <span className="text-[10px] font-semibold text-chart-5 uppercase tracking-wider">
                    {t('timeoutLabel')}
                  </span>
                  <select
                    value={timeoutValue === null ? '' : String(timeoutValue)}
                    onChange={(e) => setTimeoutValue(e.target.value ? Number(e.target.value) : null)}
                    className="w-full text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-chart-5"
                    autoFocus
                  >
                    <option value="">{t('timeoutDefault')}</option>
                    {TIMEOUT_PRESETS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {t(p.labelKey)}
                      </option>
                    ))}
                  </select>
                  <div className="flex gap-1">
                    <button
                      onClick={() => handleSaveTimeout(timeoutValue)}
                      className="text-[10px] px-2 py-0.5 rounded bg-chart-5 text-white hover:bg-chart-5/80"
                    >
                      {t('save')}
                    </button>
                    <button
                      onClick={() => setEditingTimeout(false)}
                      className="text-[10px] px-2 py-0.5 rounded hover:bg-muted"
                    >
                      {t('cancel')}
                    </button>
                  </div>
                </div>
              ) : task.max_runtime_seconds != null ? (
                <span
                  className="inline-flex text-[10px] px-1.5 py-0.5 rounded-full bg-chart-5/10 text-chart-5 border border-chart-5/20 mt-1 cursor-pointer hover:border-chart-5/40 transition-colors"
                  onClick={() => {
                    setTimeoutValue(task.max_runtime_seconds ?? null);
                    setEditingTimeout(true);
                  }}
                >
                  {t('timeoutLabel')}: {formatDuration(task.max_runtime_seconds)}
                </span>
              ) : (
                <button
                  onClick={() => {
                    setTimeoutValue(null);
                    setEditingTimeout(true);
                  }}
                  className="text-[10px] text-muted-foreground hover:text-chart-5 transition-colors mt-1"
                >
                  + {t('timeoutLabel')}
                </button>
              )}
              {editingSkills ? (
                <div className="mt-1 rounded border border-chart-3/30 bg-chart-3/5 px-2 py-1.5 space-y-1">
                  <span className="text-[10px] font-semibold text-chart-3 uppercase tracking-wider">
                    {t('skillsLabel')}
                  </span>
                  <input
                    value={skillsText}
                    onChange={(e) => setSkillsText(e.target.value)}
                    placeholder={t('skillsPlaceholder')}
                    className="w-full text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-chart-3"
                    autoFocus
                    onKeyDown={(e) => e.key === 'Enter' && handleSaveSkills()}
                  />
                  <div className="flex gap-1">
                    <button
                      onClick={handleSaveSkills}
                      className="text-[10px] px-2 py-0.5 rounded bg-chart-3 text-white hover:bg-chart-3/80"
                    >
                      {t('save')}
                    </button>
                    <button
                      onClick={() => setEditingSkills(false)}
                      className="text-[10px] px-2 py-0.5 rounded hover:bg-muted"
                    >
                      {t('cancel')}
                    </button>
                  </div>
                </div>
              ) : task.extra_skill_ids && task.extra_skill_ids.length > 0 ? (
                <div
                  className="flex flex-wrap gap-1 mt-1 cursor-pointer group/skills"
                  onClick={() => {
                    setSkillsText(task.extra_skill_ids.join(', '));
                    setEditingSkills(true);
                  }}
                >
                  {task.extra_skill_ids.map((sid) => (
                    <span
                      key={sid}
                      className="inline-flex text-[10px] px-1.5 py-0.5 rounded-full bg-chart-3/10 text-chart-3 border border-chart-3/20 group-hover/skills:border-chart-3/40 transition-colors"
                    >
                      {sid}
                    </span>
                  ))}
                </div>
              ) : (
                <button
                  onClick={() => {
                    setSkillsText('');
                    setEditingSkills(true);
                  }}
                  className="text-[10px] text-muted-foreground hover:text-chart-3 transition-colors mt-1"
                >
                  + {t('skillsLabel')}
                </button>
              )}
              {task.status === 'running' && task.progress_note && (
                <p className="text-xs text-chart-4 bg-chart-4/5 rounded px-2 py-1 mt-1 font-medium">
                  {task.progress_note}
                </p>
              )}
              {task.blocked_reason && (
                <div className="text-xs text-destructive bg-destructive/5 rounded px-2 py-1 mt-1 space-y-0.5">
                  <p className="flex items-center gap-1">
                    {task.block_kind === 'scheduled' && <Clock className="w-3.5 h-3.5 shrink-0" />}
                    {task.block_kind === 'external' && <ExternalLink className="w-3.5 h-3.5 shrink-0" />}
                    {task.block_kind === 'human' && <User className="w-3.5 h-3.5 shrink-0" />}
                    <span className="font-medium capitalize">{task.block_kind ?? 'blocked'}</span>
                    <span className="text-muted-foreground">—</span>
                    {task.blocked_reason}
                  </p>
                  {task.block_kind === 'scheduled' && task.scheduled_until && (
                    <p className="text-[10px] text-chart-4 font-mono">
                      {t('autoUnblockAt')}: {new Date(task.scheduled_until).toLocaleString()}
                    </p>
                  )}
                </div>
              )}
              <div className="mt-1.5">
                {editingCriteria ? (
                  <div className="rounded border border-primary/30 bg-primary/5 px-2 py-1.5 space-y-1.5">
                    <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">
                      {t('completionCriteria')}
                    </span>
                    <textarea
                      value={criteriaText}
                      onChange={(e) => setCriteriaText(e.target.value)}
                      placeholder={t('criteriaPlaceholder')}
                      className="w-full text-xs px-2 py-1.5 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                      rows={3}
                      autoFocus
                    />
                    <div className="flex gap-1.5">
                      <button
                        onClick={handleSaveCriteria}
                        disabled={savingCriteria}
                        className="text-[10px] px-2 py-0.5 rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        {t('send')}
                      </button>
                      <button
                        onClick={() => setEditingCriteria(false)}
                        className="text-[10px] px-2 py-0.5 rounded hover:bg-muted"
                      >
                        {t('cancel')}
                      </button>
                    </div>
                  </div>
                ) : task.completion_criteria ? (
                  <div
                    className="rounded border border-primary/20 bg-primary/5 px-2 py-1.5 cursor-pointer hover:border-primary/40 transition-colors group/criteria"
                    onClick={() => {
                      setCriteriaText(task.completion_criteria ?? '');
                      setEditingCriteria(true);
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">
                        {t('completionCriteria')}
                      </span>
                      <span className="text-[9px] text-primary/50 opacity-0 group-hover/criteria:opacity-100 transition-opacity">
                        {t('editCriteria')}
                      </span>
                    </div>
                    <KanbanMarkdown className="text-foreground/80 mt-0.5">{task.completion_criteria}</KanbanMarkdown>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setCriteriaText('');
                      setEditingCriteria(true);
                    }}
                    className="text-[10px] text-primary/60 hover:text-primary transition-colors"
                  >
                    + {t('completionCriteria')}
                  </button>
                )}
              </div>

              {/* Agent assignment */}
              {agents.length > 0 && (
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-[10px] text-muted-foreground font-medium shrink-0">{t('assignedAgent')}:</span>
                  {assignedAgent?.avatar_url ? (
                    <img
                      src={assignedAgent.avatar_url}
                      alt={assignedAgent.name}
                      className="w-4 h-4 rounded-full shrink-0 object-cover"
                    />
                  ) : task.agent_id && agentName ? (
                    <span className="w-4 h-4 rounded-full shrink-0 bg-chart-4/20 text-chart-4 text-[8px] font-bold flex items-center justify-center">
                      {agentName.charAt(0).toUpperCase()}
                    </span>
                  ) : null}
                  <select
                    value={task.agent_id ?? ''}
                    onChange={(e) => handleAgentChange(e.target.value || null)}
                    className="text-[10px] px-1.5 py-0.5 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary max-w-[140px]"
                  >
                    <option value="">{t('unassigned')}</option>
                    {agents.map((ag) => (
                      <option key={ag.id} value={ag.id}>
                        {ag.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Attachments */}
            <section
              className={cn(
                'rounded-lg border px-3 py-2 transition-colors',
                dragOver ? 'border-primary bg-primary/5' : 'border-border',
              )}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false);
              }}
              onDrop={handleDrop}
            >
              <div className="flex items-center justify-between mb-1.5">
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                  <Paperclip className="w-3 h-3" />
                  {t('attachments')}
                  {(task.attachments ?? []).length > 0 && (
                    <span className="text-[10px] text-primary font-normal">({(task.attachments ?? []).length})</span>
                  )}
                </h4>
                <button
                  onClick={() => attachInputRef.current?.click()}
                  disabled={uploadingAttachment}
                  className="text-[10px] px-1.5 py-0.5 rounded hover:bg-primary/10 text-primary/70 hover:text-primary transition-colors disabled:opacity-50"
                >
                  {uploadingAttachment ? t('uploading') : `+ ${t('addAttachment')}`}
                </button>
                <input
                  ref={attachInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    e.target.value = '';
                    handleAttachUpload(files);
                  }}
                />
              </div>
              {(task.attachments ?? []).length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                  {(task.attachments ?? []).map((att) => {
                    const isImage = att.content_type.startsWith('image/');
                    return (
                      <div key={att.file_id} className="group/att relative rounded border bg-muted/30 overflow-hidden">
                        {isImage ? (
                          <a href={att.url} target="_blank" rel="noopener noreferrer" className="block">
                            <img
                              src={att.url}
                              alt={att.filename}
                              className="w-full h-16 object-cover hover:opacity-80 transition-opacity"
                              loading="lazy"
                            />
                          </a>
                        ) : (
                          <a
                            href={att.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 px-2 py-2 hover:bg-muted/50 transition-colors"
                          >
                            <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                            <span className="text-[10px] text-foreground/80 truncate">{att.filename}</span>
                          </a>
                        )}
                        <button
                          onClick={() => handleRemoveAttachment(att.file_id)}
                          className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-destructive/80 text-destructive-foreground flex items-center justify-center opacity-0 group-hover/att:opacity-100 transition-opacity"
                          title={t('removeAttachment')}
                        >
                          <X className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[10px] text-muted-foreground/60 text-center py-2">
                  {dragOver ? t('dropFilesHere') : t('noAttachments')}
                </p>
              )}
            </section>

            <KanbanDiagnosticsSection
              diagnostics={diagnostics}
              onMove={handleMove}
              onFocusComment={() => {
                commentInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                setTimeout(() => commentInputRef.current?.focus(), 300);
              }}
            />

            {/* Latest progress */}
            {latestSummary && (
              <div className="rounded-lg border bg-muted/20 px-3 py-2">
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                  {t('latestProgress')}
                </h4>
                <KanbanMarkdown className="text-foreground/80" maxLines={4}>
                  {latestSummary}
                </KanbanMarkdown>
              </div>
            )}

            {/* Dependencies */}
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
                        <span className="text-[9px] text-muted-foreground shrink-0">
                          ({t(`status.${parent.status}`)})
                        </span>
                      </button>
                      <button
                        onClick={() => handleRemoveDep(parent.task_id)}
                        className="text-[9px] text-destructive/50 hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
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
                        <span className="text-[9px] text-muted-foreground shrink-0 ml-auto">
                          {t(`status.${t2.status}`)}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </section>

            {/* Dependents (children) */}
            {children.length > 0 && (
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
                  {children.map((child) => (
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

            <KanbanRunHistory runs={runs} />
            <KanbanEventTimeline events={events} />

            {/* Comment input */}
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
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
