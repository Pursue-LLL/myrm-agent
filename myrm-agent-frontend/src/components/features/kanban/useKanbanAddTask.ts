/**
 * [INPUT]
 * - @/services/kanban::createTask (POS: 看板 API 层)
 * - next-intl::useTranslations (POS: 国际化翻译)
 *
 * [OUTPUT]
 * - useKanbanAddTask: 看板任务内联创建表单状态管理 hook
 *
 * [POS]
 * 看板新增任务表单逻辑层。管理标题/描述/依赖/技能/超时等表单状态，封装提交和重置操作。
 */
'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';
import type { TaskStatus } from '@/services/kanban';
import { createTask } from '@/services/kanban';
import type { KanbanAttachment } from './KanbanInlineAddForm';

interface UseKanbanAddTaskOptions {
  boardId: string;
  onCreated: () => Promise<void>;
}

export function useKanbanAddTask({ boardId, onCreated }: UseKanbanAddTaskOptions) {
  const t = useTranslations('kanban');
  const [addingColumn, setAddingColumn] = useState<TaskStatus | null>(null);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskDesc, setNewTaskDesc] = useState('');
  const [selectedDeps, setSelectedDeps] = useState<string[]>([]);
  const [showDepPicker, setShowDepPicker] = useState(false);
  const [showCriteria, setShowCriteria] = useState(false);
  const [newTaskCriteria, setNewTaskCriteria] = useState('');
  const [newTaskAgentId, setNewTaskAgentId] = useState<string>('');
  const [newTaskSkills, setNewTaskSkills] = useState('');
  const [newTaskMaxRuntime, setNewTaskMaxRuntime] = useState<number | null>(null);
  const [newTaskBranch, setNewTaskBranch] = useState('');
  const [newTaskAttachments, setNewTaskAttachments] = useState<KanbanAttachment[]>([]);

  const toggleDep = (taskId: string) => {
    setSelectedDeps((prev) => (prev.includes(taskId) ? prev.filter((id) => id !== taskId) : [...prev, taskId]));
  };

  const resetAddForm = useCallback(() => {
    setAddingColumn(null);
    setNewTaskTitle('');
    setNewTaskDesc('');
    setSelectedDeps([]);
    setShowDepPicker(false);
    setShowCriteria(false);
    setNewTaskCriteria('');
    setNewTaskMaxRuntime(null);
    setNewTaskBranch('');
    setNewTaskAttachments([]);
  }, []);

  const handleAddTask = useCallback(async () => {
    if (!newTaskTitle.trim()) return;
    const isTriageColumn = addingColumn === 'triage';
    try {
      const parsedSkills = newTaskSkills
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const attachmentIds = newTaskAttachments.map((a) => a.file_id);
      await createTask(boardId, {
        title: newTaskTitle.trim(),
        description: newTaskDesc.trim() || undefined,
        priority: 'normal',
        depends_on: selectedDeps.length > 0 ? selectedDeps : undefined,
        extra_skill_ids: parsedSkills.length > 0 ? parsedSkills : undefined,
        attachment_ids: attachmentIds.length > 0 ? attachmentIds : undefined,
        completion_criteria: newTaskCriteria.trim() || undefined,
        agent_id: newTaskAgentId || undefined,
        max_runtime_seconds: newTaskMaxRuntime ?? undefined,
        branch: newTaskBranch.trim() || undefined,
        initial_status: isTriageColumn ? 'triage' : undefined,
      });
      setNewTaskTitle('');
      setNewTaskDesc('');
      setSelectedDeps([]);
      setShowDepPicker(false);
      setShowCriteria(false);
      setNewTaskCriteria('');
      setNewTaskAgentId('');
      setNewTaskSkills('');
      setNewTaskMaxRuntime(null);
      setNewTaskBranch('');
      setNewTaskAttachments([]);
      setAddingColumn(null);
      await onCreated();
      toast.success(t('taskAdded'));
    } catch {
      toast.error(t('addError'));
    }
  }, [
    boardId,
    newTaskTitle,
    newTaskDesc,
    newTaskCriteria,
    newTaskAgentId,
    newTaskSkills,
    newTaskMaxRuntime,
    newTaskBranch,
    newTaskAttachments,
    selectedDeps,
    addingColumn,
    onCreated,
    t,
  ]);

  return {
    addingColumn,
    setAddingColumn,
    newTaskTitle,
    setNewTaskTitle,
    newTaskDesc,
    setNewTaskDesc,
    selectedDeps,
    showDepPicker,
    setShowDepPicker,
    showCriteria,
    setShowCriteria,
    newTaskCriteria,
    setNewTaskCriteria,
    newTaskAgentId,
    setNewTaskAgentId,
    newTaskSkills,
    setNewTaskSkills,
    newTaskMaxRuntime,
    setNewTaskMaxRuntime,
    newTaskBranch,
    setNewTaskBranch,
    newTaskAttachments,
    setNewTaskAttachments,
    toggleDep,
    resetAddForm,
    handleAddTask,
  };
}
