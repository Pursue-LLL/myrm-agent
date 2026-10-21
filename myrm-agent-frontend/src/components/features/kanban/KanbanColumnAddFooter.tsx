/**
 * [INPUT]
 * - ./KanbanInlineAddForm (POS: 看板内联新增任务表单)
 * - ./useKanbanAddTask (POS: 看板新增任务表单逻辑层，状态由主视图持有)
 *
 * [OUTPUT]
 * - KanbanColumnAddFooter (default): Triage / Ready 列底部的「新增」入口，展开后是内联新增表单
 *
 * [POS]
 * 看板列的新增任务入口。表单状态来自主视图持有的 useKanbanAddTask，同一时刻只有一列处于展开状态。
 */
'use client';

import type { ComponentProps } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask } from '@/services/kanban';
import KanbanInlineAddForm from './KanbanInlineAddForm';
import type { useKanbanAddTask } from './useKanbanAddTask';

interface KanbanColumnAddFooterProps {
  status: ComponentProps<typeof KanbanInlineAddForm>['variant'];
  addTask: ReturnType<typeof useKanbanAddTask>;
  allTasks: KanbanTask[];
  agents: ComponentProps<typeof KanbanInlineAddForm>['agents'];
  enabledModels: ComponentProps<typeof KanbanInlineAddForm>['enabledModels'];
}

export default function KanbanColumnAddFooter({
  status,
  addTask,
  allTasks,
  agents,
  enabledModels,
}: KanbanColumnAddFooterProps) {
  const t = useTranslations('kanban');
  const {
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
    newTaskModelOverride,
    setNewTaskModelOverride,
    newTaskSkills,
    setNewTaskSkills,
    newTaskMaxRuntime,
    setNewTaskMaxRuntime,
    newTaskBranch,
    setNewTaskBranch,
    newTaskGoalMode,
    setNewTaskGoalMode,
    newTaskGoalMaxTurns,
    setNewTaskGoalMaxTurns,
    newTaskRequireApproval,
    setNewTaskRequireApproval,
    newTaskAttachments,
    setNewTaskAttachments,
    toggleDep,
    resetAddForm,
    handleAddTask,
  } = addTask;

  return (
    <div className="mt-1">
      {addingColumn === status ? (
        <KanbanInlineAddForm
          variant={status}
          title={newTaskTitle}
          description={newTaskDesc}
          selectedDeps={selectedDeps}
          showDepPicker={showDepPicker}
          showCriteria={showCriteria}
          criteria={newTaskCriteria}
          agentId={newTaskAgentId}
          modelOverride={newTaskModelOverride}
          skills={newTaskSkills}
          maxRuntimeSeconds={newTaskMaxRuntime}
          branch={newTaskBranch}
          goalMode={newTaskGoalMode}
          goalMaxTurns={newTaskGoalMaxTurns}
          requireApproval={newTaskRequireApproval}
          agents={agents}
          enabledModels={enabledModels}
          allTasks={allTasks}
          attachments={newTaskAttachments}
          onAttachmentsChange={setNewTaskAttachments}
          onTitleChange={setNewTaskTitle}
          onDescriptionChange={setNewTaskDesc}
          onSelectedDepsToggle={toggleDep}
          onShowDepPickerToggle={() => setShowDepPicker((v) => !v)}
          onShowCriteriaToggle={() => setShowCriteria((v) => !v)}
          onCriteriaChange={setNewTaskCriteria}
          onAgentIdChange={setNewTaskAgentId}
          onModelOverrideChange={setNewTaskModelOverride}
          onSkillsChange={setNewTaskSkills}
          onMaxRuntimeChange={setNewTaskMaxRuntime}
          onBranchChange={setNewTaskBranch}
          onGoalModeChange={setNewTaskGoalMode}
          onGoalMaxTurnsChange={setNewTaskGoalMaxTurns}
          onRequireApprovalChange={setNewTaskRequireApproval}
          onSubmit={handleAddTask}
          onCancel={resetAddForm}
        />
      ) : (
        <button
          onClick={() => setAddingColumn(status)}
          data-testid={`kanban-add-task-${status}`}
          className={cn(
            'w-full flex items-center justify-center gap-1 text-xs py-1.5 rounded hover:bg-background/50 transition-colors',
            status === 'triage'
              ? 'text-purple-600/80 dark:text-purple-400/80 hover:text-purple-600 dark:hover:text-purple-400'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          + {status === 'triage' ? t('addIdea') : t('addTask')}
        </button>
      )}
    </div>
  );
}
