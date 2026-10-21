/**
 * [INPUT]
 * - ./useKanbanTaskDrawer (POS: 抽屉全部数据与操作)
 * - ./KanbanTaskDrawerHeader、./KanbanTaskDrawerDetails、./KanbanTaskDrawerBodySections、./KanbanTaskDrawerBodyMetaSections (POS: 各区段组件)
 * - ./RaceSection、./KanbanTaskHandoffSection、./KanbanDiagnosticsSection、./KanbanEventTimeline、./KanbanTaskExecutionTraceSection (POS: 赛马、交接、诊断、运行与事件、执行轨迹)
 * - @/components/primitives/sheet (POS: 右侧抽屉基础组件)
 *
 * [OUTPUT]
 * - KanbanTaskDrawer (default): 任务详情右侧抽屉，按「状态操作 -> 详情 -> 附件 -> 诊断 -> 结果 -> 最近进展 -> 交接 -> 赛马 -> 依赖 -> 运行历史 -> 事件 -> 执行轨迹 -> 评论」的顺序排布各区段
 *
 * [POS]
 * 看板任务的详情与编辑入口。状态与操作都在 useKanbanTaskDrawer，本组件只负责布局和区段顺序。
 */
'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/primitives/sheet';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { STATUS_DOT } from './kanban-styles';
import { useAgentName } from '@/hooks/agent/useAgentName';
import { useKanbanTaskDrawer } from './useKanbanTaskDrawer';
import { StatusActionsBar } from './KanbanTaskDrawerHeader';
import { TaskDetailsSection } from './KanbanTaskDrawerDetails';
import { AttachmentsSection, TaskResultSection } from './KanbanTaskDrawerBodySections';
import { DependenciesSection, CommentInputSection, LatestProgressSection } from './KanbanTaskDrawerBodyMetaSections';
import RaceSection from './RaceSection';
import { KanbanTaskHandoffSection } from './KanbanTaskHandoffSection';
import KanbanDiagnosticsSection from './KanbanDiagnosticsSection';
import KanbanTaskExecutionTraceSection from './KanbanTaskExecutionTraceSection';
import { KanbanRunHistory, KanbanEventTimeline } from './KanbanEventTimeline';
import type { KanbanModelOption } from './KanbanInlineAddForm';

interface KanbanTaskDrawerProps {
  task: KanbanTask | null;
  allTasks: KanbanTask[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRefresh: () => void;
  onRequestMove: (taskId: string, targetStatus: TaskStatus) => void;
  onNavigateTask?: (taskId: string) => void;
  enabledModels: KanbanModelOption[];
}

export default function KanbanTaskDrawer({
  task,
  allTasks,
  open,
  onOpenChange,
  onRefresh,
  onRequestMove,
  onNavigateTask,
  enabledModels,
}: KanbanTaskDrawerProps) {
  const t = useTranslations('kanban');
  const agentName = useAgentName(task?.agent_id);

  const drawer = useKanbanTaskDrawer({ task, allTasks, open, onOpenChange, onRefresh, onRequestMove, t });

  if (!task) {
    return null;
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:w-[400px] sm:max-w-[440px] overflow-y-auto p-0"
        hideCloseButton
        data-testid="kanban-task-drawer"
      >
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

          <StatusActionsBar
            task={task}
            promoting={drawer.promoting}
            showReclaimDialog={drawer.showReclaimDialog}
            setShowReclaimDialog={drawer.setShowReclaimDialog}
            reclaimReason={drawer.reclaimReason}
            setReclaimReason={drawer.setReclaimReason}
            reclaimAgentId={drawer.reclaimAgentId}
            setReclaimAgentId={drawer.setReclaimAgentId}
            reclaiming={drawer.reclaiming}
            agents={drawer.agents}
            promoteConfirm={drawer.promoteConfirm}
            setPromoteConfirm={drawer.setPromoteConfirm}
            handleMove={drawer.handleMove}
            handleReclaim={drawer.handleReclaim}
            handleForcePromote={drawer.handleForcePromote}
            showRejectDialog={drawer.showRejectDialog}
            setShowRejectDialog={drawer.setShowRejectDialog}
            rejectReason={drawer.rejectReason}
            setRejectReason={drawer.setRejectReason}
            approving={drawer.approving}
            rejecting={drawer.rejecting}
            handleApprove={drawer.handleApprove}
            handleReject={drawer.handleReject}
            t={t}
          />
        </div>

        {drawer.loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-lg bg-muted/30 animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="p-4 space-y-4">
            <TaskDetailsSection
              task={task}
              agentName={agentName}
              progressPill={drawer.progressPill}
              editingTimeout={drawer.editingTimeout}
              setEditingTimeout={drawer.setEditingTimeout}
              timeoutValue={drawer.timeoutValue}
              setTimeoutValue={drawer.setTimeoutValue}
              handleSaveTimeout={drawer.handleSaveTimeout}
              editingSkills={drawer.editingSkills}
              setEditingSkills={drawer.setEditingSkills}
              skillsText={drawer.skillsText}
              setSkillsText={drawer.setSkillsText}
              handleSaveSkills={drawer.handleSaveSkills}
              editingCriteria={drawer.editingCriteria}
              setEditingCriteria={drawer.setEditingCriteria}
              criteriaText={drawer.criteriaText}
              setCriteriaText={drawer.setCriteriaText}
              savingCriteria={drawer.savingCriteria}
              handleSaveCriteria={drawer.handleSaveCriteria}
              assignedAgent={drawer.assignedAgent}
              agents={drawer.agents}
              handleAgentChange={drawer.handleAgentChange}
              enabledModels={enabledModels}
              editingModel={drawer.editingModel}
              setEditingModel={drawer.setEditingModel}
              modelValue={drawer.modelValue}
              setModelValue={drawer.setModelValue}
              handleSaveModel={drawer.handleSaveModel}
              handleRequireApprovalChange={drawer.handleRequireApprovalChange}
              t={t}
            />

            <AttachmentsSection
              task={task}
              dragOver={drawer.dragOver}
              setDragOver={drawer.setDragOver}
              uploadingAttachment={drawer.uploadingAttachment}
              attachInputRef={drawer.attachInputRef}
              handleDrop={drawer.handleDrop}
              handleAttachUpload={drawer.handleAttachUpload}
              handleRemoveAttachment={drawer.handleRemoveAttachment}
              t={t}
            />

            <KanbanDiagnosticsSection
              diagnostics={drawer.diagnostics}
              onMove={drawer.handleMove}
              onFocusComment={() => {
                drawer.commentInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                setTimeout(() => drawer.commentInputRef.current?.focus(), 300);
              }}
            />

            <TaskResultSection
              task={task}
              isTerminal={drawer.isTerminal}
              editingResult={drawer.editingResult}
              setEditingResult={drawer.setEditingResult}
              resultText={drawer.resultText}
              setResultText={drawer.setResultText}
              savingResult={drawer.savingResult}
              handleSaveResult={drawer.handleSaveResult}
              t={t}
            />

            <LatestProgressSection latestSummary={drawer.latestSummary} t={t} />

            <KanbanTaskHandoffSection task={task} onChanged={onRefresh} t={t} />

            <RaceSection boardId={task.board_id} task={task} onChanged={onRefresh} t={t} />

            <DependenciesSection
              parents={drawer.parents}
              dependents={drawer.children}
              showAddDep={drawer.showAddDep}
              setShowAddDep={drawer.setShowAddDep}
              addingDep={drawer.addingDep}
              availableParents={drawer.availableParents}
              progressPill={drawer.progressPill}
              handleAddDep={drawer.handleAddDep}
              handleRemoveDep={drawer.handleRemoveDep}
              onNavigateTask={onNavigateTask}
              t={t}
            />

            <KanbanRunHistory runs={drawer.runs} />
            <KanbanEventTimeline events={drawer.events} />

            <KanbanTaskExecutionTraceSection taskId={task.task_id} taskStatus={task.status} />

            <CommentInputSection
              commentText={drawer.commentText}
              setCommentText={drawer.setCommentText}
              submittingComment={drawer.submittingComment}
              commentInputRef={drawer.commentInputRef}
              handleSubmitComment={drawer.handleSubmitComment}
              t={t}
            />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
