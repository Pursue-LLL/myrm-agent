/**
 * [INPUT]
 * - @/services/kanban::listRuns, listEvents, listDependencies, listDependents, addComment, addDependency, removeDependency (POS: 运行记录、事件、依赖、评论 API)
 * - ./resolveTaskDepInfos (POS: 依赖摘要解析，本地列表优先、远程兜底)
 *
 * [OUTPUT]
 * - useKanbanTaskCardDetails: 任务卡片展开详情的状态与操作（运行记录、事件、依赖增删、评论）
 * - KanbanTaskCardDetailsState: 上述 hook 的返回类型，详情面板组件的入参
 *
 * [POS]
 * 任务卡片的展开详情数据层。详情在首次展开时才加载，加载失败保持空面板；依赖与评论的写入成功后更新本地列表，
 * 并通过 onRefresh 让看板重新取数。
 */
'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  addComment,
  addDependency,
  listDependencies,
  listDependents,
  listEvents,
  listRuns,
  removeDependency,
  type KanbanTask,
  type TaskEvent,
  type TaskRun,
} from '@/services/kanban';
import type { TaskDepInfo } from './kanban-styles';
import { resolveTaskDepInfos } from './resolveTaskDepInfos';

interface UseKanbanTaskCardDetailsOptions {
  task: KanbanTask;
  allTasks: KanbanTask[];
  onRefresh: () => void;
}

export function useKanbanTaskCardDetails({ task, allTasks, onRefresh }: UseKanbanTaskCardDetailsOptions) {
  const t = useTranslations('kanban');
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

      const [parentInfos, childInfos] = await Promise.all([
        resolveTaskDepInfos(depsRes.items, allTasks),
        resolveTaskDepInfos(childRes.items, allTasks),
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
        const parentTask = allTasks.find((candidate) => candidate.task_id === parentId);
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
    if (!commentText.trim()) {
      return;
    }
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
    (candidate) => candidate.task_id !== task.task_id && !parents.some((p) => p.task_id === candidate.task_id),
  );

  return {
    expanded,
    toggleExpand,
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
  };
}

export type KanbanTaskCardDetailsState = ReturnType<typeof useKanbanTaskCardDetails>;
