import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
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
import type { TaskDepInfo } from './kanban-styles';
import useAgentStore from '@/store/useAgentStore';
import { getApiUrl } from '@/lib/api';

interface UseKanbanTaskDrawerParams {
  task: KanbanTask | null;
  allTasks: KanbanTask[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRefresh: () => void;
  t: (key: string) => string;
}

export function useKanbanTaskDrawer({ task, allTasks, open, onOpenChange, onRefresh, t }: UseKanbanTaskDrawerParams) {
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
  const [editingResult, setEditingResult] = useState(false);
  const [resultText, setResultText] = useState('');
  const [savingResult, setSavingResult] = useState(false);

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

  const handleSaveResult = useCallback(async () => {
    if (!task) return;
    setSavingResult(true);
    try {
      await updateTask(task.task_id, { result: resultText });
      setEditingResult(false);
      onRefresh();
      toast.success(t('resultUpdated'));
    } catch {
      toast.error(t('updateError'));
    } finally {
      setSavingResult(false);
    }
  }, [task, resultText, onRefresh, t]);

  const isTerminal = task?.status === 'completed' || task?.status === 'failed' || task?.status === 'archived';

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

  return {
    agents,
    runs,
    events,
    parents,
    children,
    diagnostics,
    loading,
    commentText,
    setCommentText,
    submittingComment,
    showAddDep,
    setShowAddDep,
    addingDep,
    editingCriteria,
    setEditingCriteria,
    criteriaText,
    setCriteriaText,
    savingCriteria,
    editingSkills,
    setEditingSkills,
    skillsText,
    setSkillsText,
    editingTimeout,
    setEditingTimeout,
    timeoutValue,
    setTimeoutValue,
    promoteConfirm,
    setPromoteConfirm,
    promoting,
    showReclaimDialog,
    setShowReclaimDialog,
    reclaimReason,
    setReclaimReason,
    reclaimAgentId,
    setReclaimAgentId,
    reclaiming,
    uploadingAttachment,
    dragOver,
    setDragOver,
    editingResult,
    setEditingResult,
    resultText,
    setResultText,
    savingResult,
    commentInputRef,
    attachInputRef,
    isTerminal,
    latestSummary,
    progressPill,
    assignedAgent,
    availableParents,
    handleMove,
    handleForcePromote,
    handleReclaim,
    handleRemoveDep,
    handleAddDep,
    handleAttachUpload,
    handleRemoveAttachment,
    handleDrop,
    handleSubmitComment,
    handleSaveCriteria,
    handleSaveSkills,
    handleSaveTimeout,
    handleAgentChange,
    handleSaveResult,
  };
}
