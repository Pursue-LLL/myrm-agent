/**
 * [INPUT]
 * - ./useKanbanBoardData、./useKanbanMoveTask、./useKanbanSelection、./useKanbanLanes、./useKanbanAddTask (POS: 看板数据、移动、多选、泳道、新增表单各自的状态层)
 * - ./useKanbanDnD、./KanbanDndComponents::KanbanDropColumn (POS: 拖拽逻辑与 DnD 渲染层)
 * - ./useKanbanTaskActions、./KanbanTaskActionConfirm (POS: 回收 / 删除 / 重试 / 归档的执行与统一确认)
 * - ./KanbanBoardHeader、./KanbanBoardStats、./KanbanViewControls、./KanbanFilterBanners、./KanbanColumnAddFooter、./KanbanMoveConfirmDialogs、./KanbanBulkActionBar (POS: 标题、统计、视图切换、筛选提示、列底部新增、移动确认框、批量工具栏)
 * - @/services/kanban (POS: 看板 API 层)
 *
 * [OUTPUT]
 * - KanbanBoardView: 看板主视图组装层（列布局 + DnD 上下文 + board / graph / activity 标签切换 + 抽屉、向导、重规划入口）
 *
 * [POS]
 * 只做组装：数据、移动、选择、泳道与新增表单分别由各自的 hook 持有，界面片段由独立组件渲染，
 * 本文件把它们接在一起并负责跨片段的联动（例如批量移动结束后让被拒的卡片保持选中）。
 */
'use client';

import { useCallback, useEffect, useEffectEvent, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useLocale, useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import { filterTasksByResponsibility, type ResponsibilityFilter } from '@/lib/kanban/kanbanDecisionFrame';
import { DndContext, DragOverlay, closestCenter } from '@dnd-kit/core';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import type { KanbanBoard, KanbanTask, TaskStatus } from '@/services/kanban';
import { specifyAllTriage } from '@/services/kanban';
import { Tabs, TabsContent } from '@/components/primitives/tabs';
import KanbanTaskCard from './KanbanTaskCard';
import KanbanTaskDrawer from './KanbanTaskDrawer';
import KanbanFilterBanners from './KanbanFilterBanners';
import KanbanBoardHeader from './KanbanBoardHeader';
import KanbanBoardStats from './KanbanBoardStats';
import KanbanViewControls, { type KanbanViewMode } from './KanbanViewControls';
import KanbanColumnAddFooter from './KanbanColumnAddFooter';
import KanbanBulkActionBar from './KanbanBulkActionBar';
import KanbanReplanDialog from './KanbanReplanDialog';
import KanbanMoveConfirmDialogs from './KanbanMoveConfirmDialogs';
import { KanbanTaskActionConfirm, useKanbanTaskActionConfirm } from './KanbanTaskActionConfirm';
import { KanbanDropColumn } from './KanbanDndComponents';
import { useKanbanDnD } from './useKanbanDnD';
import { useKanbanTaskActions } from './useKanbanTaskActions';
import { useKanbanAddTask } from './useKanbanAddTask';
import { useKanbanBoardData } from './useKanbanBoardData';
import { useKanbanMoveTask } from './useKanbanMoveTask';
import { useKanbanLanes } from './useKanbanLanes';
import { STATUS_COLUMNS } from './kanban-styles';
import { useKanbanSelection } from './useKanbanSelection';
import { useAgentNameMap } from '@/hooks/agent/useAgentName';
import useAgentStore from '@/store/useAgentStore';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';

const KanbanGraphView = dynamic(() => import('./KanbanGraphView'), { ssr: false });
const KanbanPipelineWizard = dynamic(() => import('./KanbanPipelineWizard'), { ssr: false });
const BoardActivityFeed = dynamic(() => import('./BoardActivityFeed'), { ssr: false });

interface KanbanBoardViewProps {
  board: KanbanBoard;
  onBack: () => void;
}

export default function KanbanBoardView({ board, onBack }: KanbanBoardViewProps) {
  const t = useTranslations('kanban');
  const locale = useLocale();
  const searchParams = useSearchParams();
  const sourceChatFilter = searchParams.get('source_chat')?.trim() || undefined;
  const statusFilter = searchParams.get('status')?.trim() || undefined;
  const activeStatusFilter: TaskStatus | undefined = (STATUS_COLUMNS as readonly string[]).includes(statusFilter ?? '')
    ? (statusFilter as TaskStatus)
    : undefined;
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  const [replanOpen, setReplanOpen] = useState(false);
  const [viewMode, setViewMode] = useState<KanbanViewMode>(() => {
    if (typeof window === 'undefined') {
      return 'board';
    }
    try {
      const stored = localStorage.getItem('kanban_view_mode');
      if (stored === 'board' || stored === 'graph' || stored === 'activity') {
        return stored;
      }
    } catch {
      /* private mode / quota */
    }
    return 'board';
  });
  const [drawerTaskId, setDrawerTaskId] = useState<string | null>(null);
  const [pipelineWizardOpen, setPipelineWizardOpen] = useState(false);
  const { laneByProfile, collapsedAgents, toggleLaneByProfile, toggleAgentCollapse } = useKanbanLanes();
  const [responsibilityFilter, setResponsibilityFilter] = useState<ResponsibilityFilter>('all');
  const {
    tasks,
    setTasks,
    loading,
    summaryData,
    edges,
    markPendingWrite,
    clearPendingWrite,
    fetchTasks,
    fetchSummary,
    fetchEdges,
  } = useKanbanBoardData({ boardId: board.board_id, sourceChatFilter, activeStatusFilter, viewMode });
  const summary = summaryData?.task_counts ?? {};
  const concurrencyLimit = summaryData?.board?.settings?.max_concurrent_tasks ?? 0;
  const concurrencyFull = concurrencyLimit > 0 && (summary.running ?? 0) >= concurrencyLimit;
  const drawerTask = useMemo(
    () => (drawerTaskId ? (tasks.find((tk) => tk.task_id === drawerTaskId) ?? null) : null),
    [drawerTaskId, tasks],
  );

  const allAgentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const ag of summaryData?.by_agent ?? []) {
      if (ag.agent_id) {
        ids.add(ag.agent_id);
      }
    }
    for (const task of tasks) {
      if (task.agent_id) {
        ids.add(task.agent_id);
      }
    }
    return [...ids];
  }, [summaryData, tasks]);
  const agentNameMap = useAgentNameMap(allAgentIds);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // Reset only when the board changes, not when resetAddForm's identity changes.
  const resetBoardScopedState = useEffectEvent(() => {
    addTask.resetAddForm();
  });
  useEffect(() => {
    resetBoardScopedState();
  }, [board.board_id]);

  const columnTasks = useMemo(() => {
    const filteredTasks = filterTasksByResponsibility(tasks, responsibilityFilter);
    const grouped: Record<TaskStatus, KanbanTask[]> = {
      triage: [],
      backlog: [],
      ready: [],
      running: [],
      blocked: [],
      in_review: [],
      completed: [],
      failed: [],
      archived: [],
    };
    for (const task of filteredTasks) {
      grouped[task.status]?.push(task);
    }
    return grouped;
  }, [tasks, responsibilityFilter]);

  const { selectedTaskIds, selectedStatuses, handleTaskSelect, selectOnly, clearSelection } = useKanbanSelection({
    boardId: board.board_id,
    tasks,
    columnTasks,
    laneByProfile,
    agentNameMap,
    collapsedAgents,
  });

  const triageCount = columnTasks.triage.length;
  const [specifyAllLoading, setSpecifyAllLoading] = useState(false);

  const addTask = useKanbanAddTask({ boardId: board.board_id, onCreated: fetchTasks });

  const getEnabledModels = useProviderStore(useShallow((state) => state.getEnabledModels));
  const kanbanEnabledModels = useMemo(() => getEnabledModels(), [getEnabledModels]);

  const handleViewModeChange = useCallback((mode: KanbanViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem('kanban_view_mode', mode);
    } catch {
      /* ignore */
    }
  }, []);

  const handleSpecifyAll = useCallback(async () => {
    if (triageCount === 0 || specifyAllLoading) {
      return;
    }
    setSpecifyAllLoading(true);
    try {
      const result = await specifyAllTriage(board.board_id, { dryRun: false });
      const okCount = result.items.filter((it) => it.ok && it.persisted).length;
      toast.success(t('specifyAllDone', { ok: okCount, total: result.total }));
      await fetchTasks();
      await fetchSummary();
    } catch {
      toast.error(t('specifyError'));
    } finally {
      setSpecifyAllLoading(false);
    }
  }, [board.board_id, triageCount, specifyAllLoading, fetchTasks, fetchSummary, t]);

  const { handleMoveTask, handleBulkMove, forcePromoteState, setForcePromoteState, handleForcePromoteConfirm } =
    useKanbanMoveTask({
      boardId: board.board_id,
      tasks,
      setTasks,
      markPendingWrite,
      clearPendingWrite,
      fetchTasks,
      onBulkSettled: selectOnly,
    });

  const {
    state: taskActionState,
    requestReclaim,
    requestDelete,
    requestMove,
    dismiss: dismissTaskAction,
  } = useKanbanTaskActionConfirm(tasks, handleMoveTask);
  const taskActions = useKanbanTaskActions({ fetchTasks, moveTask: handleMoveTask });

  const {
    sensors,
    accessibility,
    draggedTaskId,
    dragOverColumn,
    dropConfirmState,
    isBulkDrag,
    handleDragStart,
    handleDragOver,
    handleDragEnd,
    handleDragCancel,
    handleDropConfirm,
    dismissDropConfirm,
  } = useKanbanDnD({
    tasks,
    selectedTaskIds,
    onMoveTask: requestMove,
    onBulkMove: handleBulkMove,
    onMoveBlocked: () => toast.error(t('moveBlocked')),
  });
  const draggedTask = draggedTaskId ? tasks.find((tk) => tk.task_id === draggedTaskId) : undefined;

  return (
    <div className="space-y-4" data-testid="kanban-board-view">
      <KanbanFilterBanners sourceChatFilter={sourceChatFilter} activeStatusFilter={activeStatusFilter} />
      <KanbanBoardHeader
        board={board}
        triageCount={triageCount}
        specifyAllLoading={specifyAllLoading}
        laneByProfile={laneByProfile}
        onBack={onBack}
        onOpenPipelineWizard={() => setPipelineWizardOpen(true)}
        onSpecifyAll={handleSpecifyAll}
        onOpenReplan={() => setReplanOpen(true)}
        onToggleLaneByProfile={toggleLaneByProfile}
        onRefresh={() => {
          fetchTasks();
          fetchSummary();
          fetchEdges();
        }}
      />
      <KanbanBoardStats
        summaryData={summaryData}
        summary={summary}
        concurrencyLimit={concurrencyLimit}
        agentNameMap={agentNameMap}
      />
      <KanbanViewControls
        viewMode={viewMode}
        responsibilityFilter={responsibilityFilter}
        onViewModeChange={handleViewModeChange}
        onResponsibilityFilterChange={setResponsibilityFilter}
      />

      <Tabs value={viewMode}>
        <TabsContent value="board" className="mt-3">
          {loading ? (
            <div className="flex gap-4">
              {STATUS_COLUMNS.map((col) => (
                <div key={col} className="flex-1 min-w-[200px] h-40 rounded-lg bg-muted/30 animate-pulse" />
              ))}
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              accessibility={accessibility}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
              onDragCancel={handleDragCancel}
            >
              <div className="flex gap-3 overflow-x-auto pb-4">
                {STATUS_COLUMNS.map((status) => (
                  <KanbanDropColumn
                    key={status}
                    status={status}
                    tasks={columnTasks[status] ?? []}
                    allTasks={tasks}
                    draggedTaskId={draggedTaskId}
                    dragOverColumn={dragOverColumn}
                    selectedTaskIds={selectedTaskIds}
                    onTaskSelect={handleTaskSelect}
                    onMoveTask={requestMove}
                    onDeleteTask={requestDelete}
                    onReclaimTask={requestReclaim}
                    onRefresh={fetchTasks}
                    onOpenTaskDrawer={setDrawerTaskId}
                    laneByProfile={laneByProfile}
                    agentNameMap={agentNameMap}
                    collapsedAgents={collapsedAgents}
                    onToggleAgentCollapse={toggleAgentCollapse}
                    queuedByConcurrency={concurrencyFull}
                    footer={
                      status === 'triage' || status === 'ready' ? (
                        <KanbanColumnAddFooter
                          status={status}
                          addTask={addTask}
                          allTasks={tasks}
                          agents={agents}
                          enabledModels={kanbanEnabledModels}
                        />
                      ) : undefined
                    }
                    t={t}
                  />
                ))}
              </div>
              <DragOverlay dropAnimation={null}>
                {draggedTask ? (
                  <div className="rounded-md shadow-lg scale-105 rotate-1 opacity-90 pointer-events-none max-w-[280px]">
                    {isBulkDrag && (
                      <div className="absolute -top-2 -right-2 z-20 w-5 h-5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center shadow">
                        {selectedTaskIds.length}
                      </div>
                    )}
                    <KanbanTaskCard
                      task={draggedTask}
                      allTasks={tasks}
                      onMove={requestMove}
                      onDelete={requestDelete}
                      onRefresh={fetchTasks}
                      onReclaim={requestReclaim}
                    />
                  </div>
                ) : null}
              </DragOverlay>
            </DndContext>
          )}
        </TabsContent>

        <TabsContent value="graph" className="mt-3">
          {loading ? (
            <div className="h-[400px] rounded-lg bg-muted/30 animate-pulse" />
          ) : (
            <KanbanGraphView tasks={tasks} edges={edges} onTaskSelect={(taskId) => setDrawerTaskId(taskId)} />
          )}
        </TabsContent>

        <TabsContent value="activity" className="mt-3">
          <div className="h-[360px] sm:h-[500px] rounded-lg border border-border/50 bg-card overflow-hidden">
            <BoardActivityFeed boardId={board.board_id} onTaskClick={(taskId) => setDrawerTaskId(taskId)} />
          </div>
        </TabsContent>
      </Tabs>

      <KanbanTaskDrawer
        task={drawerTask}
        allTasks={tasks}
        open={drawerTaskId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDrawerTaskId(null);
          }
        }}
        onRefresh={fetchTasks}
        onRequestMove={requestMove}
        onNavigateTask={setDrawerTaskId}
        enabledModels={kanbanEnabledModels}
      />

      <KanbanPipelineWizard
        boardId={board.board_id}
        open={pipelineWizardOpen}
        onClose={() => setPipelineWizardOpen(false)}
        onCreated={() => {
          fetchTasks();
          fetchSummary();
          fetchEdges();
        }}
      />

      <KanbanReplanDialog
        board={board}
        open={replanOpen}
        onOpenChange={setReplanOpen}
        proposedChanges={[]}
        onApplied={() => {
          fetchTasks();
          fetchSummary();
          fetchEdges();
        }}
      />

      <KanbanBulkActionBar
        boardId={board.board_id}
        selectedIds={selectedTaskIds}
        selectedStatuses={selectedStatuses}
        onClear={clearSelection}
        onComplete={(failedTaskIds) => {
          selectOnly(failedTaskIds);
          fetchTasks();
          fetchSummary();
        }}
        agents={agents.map((ag) => ({ id: ag.id, name: getBuiltinAgentName(ag.id, ag.name, locale) }))}
      />

      <KanbanMoveConfirmDialogs
        forcePromoteState={forcePromoteState}
        onForcePromoteDismiss={() => setForcePromoteState(null)}
        onForcePromoteConfirm={handleForcePromoteConfirm}
        dropConfirmState={dropConfirmState}
        onDropDismiss={dismissDropConfirm}
        onDropConfirm={handleDropConfirm}
      />

      <KanbanTaskActionConfirm
        state={taskActionState}
        onDismiss={dismissTaskAction}
        onReclaim={taskActions.reclaim}
        onDelete={taskActions.remove}
        onRetry={taskActions.retry}
        onArchive={taskActions.archive}
      />
    </div>
  );
}
