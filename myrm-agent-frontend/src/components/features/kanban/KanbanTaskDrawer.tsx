'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/primitives/sheet';
import type { KanbanTask } from '@/services/kanban';
import { STATUS_DOT } from './kanban-styles';
import { useAgentName } from '@/hooks/useAgentName';
import { useKanbanTaskDrawer } from './useKanbanTaskDrawer';
import { StatusActionsBar } from './KanbanTaskDrawerHeader';
import { TaskDetailsSection } from './KanbanTaskDrawerDetails';
import {
  AttachmentsSection,
  TaskResultSection,
  DependenciesSection,
  CommentInputSection,
  LatestProgressSection,
} from './KanbanTaskDrawerBody';
import KanbanDiagnosticsSection from './KanbanDiagnosticsSection';
import { KanbanRunHistory, KanbanEventTimeline } from './KanbanEventTimeline';

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

  const drawer = useKanbanTaskDrawer({ task, allTasks, open, onOpenChange, onRefresh, t });

  if (!task) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-[400px] sm:max-w-[440px] overflow-y-auto p-0"
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

            <DependenciesSection
              task={task}
              parents={drawer.parents}
              children={drawer.children}
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
