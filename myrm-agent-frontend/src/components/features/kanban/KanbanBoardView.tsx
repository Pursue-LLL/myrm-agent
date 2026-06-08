/**
 * [INPUT]
 * - ./useKanbanDnD (POS: 看板拖拽逻辑层)
 * - ./useKanbanAddTask (POS: 看板新增任务表单逻辑层)
 * - ./KanbanDndComponents::KanbanDropColumn (POS: 看板 DnD 渲染组件层)
 * - @/services/kanban (POS: 看板 API 层)
 *
 * [OUTPUT]
 * - KanbanBoardView: 看板主视图组件（列布局 + DnD + 批量操作 + 依赖图 tab + Agent 泳道切换）
 *
 * [POS]
 * 看板全功能主视图。整合拖拽、批量操作、任务 CRUD、模板创建、规范化、Agent 泳道状态管理等所有看板交互。
 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import { Layers, Sparkles, Users } from 'lucide-react';
import { DndContext, DragOverlay, closestCenter } from '@dnd-kit/core';
import type { KanbanBoard, KanbanTask, TaskStatus, TaskDependency, BoardSummary } from '@/services/kanban';
import {
  listTasks,
  moveTask,
  deleteTask,
  reclaimTask,
  getBoardSummary,
  listBoardEdges,
  specifyAllTriage,
} from '@/services/kanban';
import { ApiError } from '@/lib/api';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives/tabs';
import KanbanTaskCard from './KanbanTaskCard';
import KanbanTaskDrawer from './KanbanTaskDrawer';
import KanbanInlineAddForm from './KanbanInlineAddForm';
import KanbanBulkActionBar from './KanbanBulkActionBar';
import { KanbanDropColumn } from './KanbanDndComponents';
import { useKanbanDnD } from './useKanbanDnD';
import { useKanbanAddTask } from './useKanbanAddTask';
import { useAgentNameMap } from '@/hooks/useAgentName';
import useAgentStore from '@/store/useAgentStore';

const KanbanGraphView = dynamic(() => import('./KanbanGraphView'), { ssr: false });
const KanbanPipelineWizard = dynamic(() => import('./KanbanPipelineWizard'), { ssr: false });
const BoardActivityFeed = dynamic(() => import('./BoardActivityFeed'), { ssr: false });

const STATUS_COLUMNS: TaskStatus[] = ['triage', 'backlog', 'ready', 'running', 'blocked', 'completed', 'failed'];

const STATUS_DOT_COLORS: Record<TaskStatus, string> = {
  triage: 'bg-purple-500',
  backlog: 'bg-muted-foreground/50',
  ready: 'bg-primary',
  running: 'bg-chart-4',
  blocked: 'bg-destructive',
  completed: 'bg-chart-2',
  failed: 'bg-destructive',
  archived: 'bg-muted-foreground/30',
};

interface KanbanBoardViewProps {
  board: KanbanBoard;
  onBack: () => void;
}

export default function KanbanBoardView({ board, onBack }: KanbanBoardViewProps) {
  const t = useTranslations('kanban');
  const [tasks, setTasks] = useState<KanbanTask[]>([]);
  const [loading, setLoading] = useState(true);
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  const [summaryData, setSummaryData] = useState<BoardSummary | null>(null);
  const summary = summaryData?.task_counts ?? {};
  const [edges, setEdges] = useState<TaskDependency[]>([]);
  const [viewMode, setViewMode] = useState<'board' | 'graph' | 'activity'>('board');
  const [drawerTaskId, setDrawerTaskId] = useState<string | null>(null);
  const [pipelineWizardOpen, setPipelineWizardOpen] = useState(false);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [laneByProfile, setLaneByProfile] = useState<boolean>(() =>
    typeof window !== 'undefined' ? localStorage.getItem('kanban_lane_by_profile') !== 'false' : true,
  );
  const [collapsedAgents, setCollapsedAgents] = useState<Set<string>>(new Set());
  const [forcePromoteState, setForcePromoteState] = useState<{
    taskId: string;
    targetStatus: TaskStatus;
    parentTitles: string[];
  } | null>(null);

  const pendingUserWrites = useRef<Map<string, { targetStatus: TaskStatus; previousStatus: TaskStatus; ts: number }>>(
    new Map(),
  );

  const handleTaskSelect = useCallback(
    (taskId: string, event: React.MouseEvent) => {
      if (event.ctrlKey || event.metaKey) {
        setSelectedTaskIds((prev) => (prev.includes(taskId) ? prev.filter((id) => id !== taskId) : [...prev, taskId]));
      } else if (event.shiftKey && selectedTaskIds.length > 0) {
        const allIds = tasks.map((tk) => tk.task_id);
        const lastIdx = allIds.indexOf(selectedTaskIds[selectedTaskIds.length - 1]);
        const currIdx = allIds.indexOf(taskId);
        if (lastIdx >= 0 && currIdx >= 0) {
          const [from, to] = lastIdx < currIdx ? [lastIdx, currIdx] : [currIdx, lastIdx];
          const rangeIds = allIds.slice(from, to + 1);
          setSelectedTaskIds((prev) => [...new Set([...prev, ...rangeIds])]);
        }
      } else {
        setSelectedTaskIds((prev) => (prev.includes(taskId) ? prev.filter((id) => id !== taskId) : [...prev, taskId]));
      }
    },
    [tasks, selectedTaskIds],
  );

  const drawerTask = useMemo(
    () => (drawerTaskId ? (tasks.find((tk) => tk.task_id === drawerTaskId) ?? null) : null),
    [drawerTaskId, tasks],
  );

  const allAgentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const ag of summaryData?.by_agent ?? []) {
      if (ag.agent_id) ids.add(ag.agent_id);
    }
    for (const task of tasks) {
      if (task.agent_id) ids.add(task.agent_id);
    }
    return [...ids];
  }, [summaryData, tasks]);
  const agentNameMap = useAgentNameMap(allAgentIds);

  const fetchTasks = useCallback(async () => {
    try {
      const result = await listTasks(board.board_id, { limit: 200 });
      const pending = pendingUserWrites.current;
      if (pending.size === 0) {
        setTasks(result.items);
      } else {
        const now = Date.now();
        for (const [id, entry] of pending) {
          if (now - entry.ts > 5_000) pending.delete(id);
        }
        setTasks(
          result.items.map((serverTask) => {
            const guard = pending.get(serverTask.task_id);
            if (guard) return { ...serverTask, status: guard.targetStatus };
            return serverTask;
          }),
        );
      }
    } catch {
      toast.error(t('fetchError'));
    } finally {
      setLoading(false);
    }
  }, [board.board_id, t]);

  const fetchEdges = useCallback(async () => {
    try {
      const result = await listBoardEdges(board.board_id);
      setEdges(result.items);
    } catch {
      /* edges are optional for the board view */
    }
  }, [board.board_id]);

  const fetchSummary = useCallback(async () => {
    try {
      const data = await getBoardSummary(board.board_id);
      setSummaryData(data);
    } catch {
      /* silent */
    }
  }, [board.board_id]);

  const reloadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleReload = useCallback(() => {
    if (reloadTimerRef.current) return;
    reloadTimerRef.current = setTimeout(() => {
      reloadTimerRef.current = null;
      fetchTasks();
      fetchSummary();
      fetchEdges();
    }, 250);
  }, [fetchTasks, fetchSummary, fetchEdges]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  useEffect(() => {
    setSelectedTaskIds([]);
  }, [board.board_id]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectedTaskIds.length > 0) {
        setSelectedTaskIds([]);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedTaskIds.length]);

  useEffect(() => {
    fetchTasks();
    fetchSummary();
    fetchEdges();
    const interval = setInterval(() => {
      fetchTasks();
      fetchSummary();
      if (viewMode === 'graph') fetchEdges();
    }, 30_000);

    const onKanbanEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail as { board_id?: string } | undefined;
      if (!detail?.board_id || detail.board_id === board.board_id) {
        scheduleReload();
      }
    };
    const onResync = () => scheduleReload();
    window.addEventListener('kanban-task-updated', onKanbanEvent);
    window.addEventListener('app_resync_required', onResync);

    return () => {
      clearInterval(interval);
      if (reloadTimerRef.current) clearTimeout(reloadTimerRef.current);
      window.removeEventListener('kanban-task-updated', onKanbanEvent);
      window.removeEventListener('app_resync_required', onResync);
    };
  }, [fetchTasks, fetchSummary, fetchEdges, viewMode, board.board_id, scheduleReload]);

  const columnTasks = useMemo(() => {
    const grouped: Record<TaskStatus, KanbanTask[]> = {
      triage: [],
      backlog: [],
      ready: [],
      running: [],
      blocked: [],
      completed: [],
      failed: [],
      archived: [],
    };
    for (const task of tasks) {
      grouped[task.status]?.push(task);
    }
    return grouped;
  }, [tasks]);

  const triageCount = columnTasks.triage.length;
  const [specifyAllLoading, setSpecifyAllLoading] = useState(false);

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
  } = useKanbanAddTask({ boardId: board.board_id, onCreated: fetchTasks });

  const toggleLaneByProfile = useCallback(() => {
    setLaneByProfile((prev) => {
      const next = !prev;
      localStorage.setItem('kanban_lane_by_profile', String(next));
      if (!next) setCollapsedAgents(new Set());
      return next;
    });
  }, []);

  const toggleAgentCollapse = useCallback((agentKey: string) => {
    setCollapsedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentKey)) next.delete(agentKey);
      else next.add(agentKey);
      return next;
    });
  }, []);

  const handleSpecifyAll = useCallback(async () => {
    if (triageCount === 0 || specifyAllLoading) return;
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

  const handleMoveTask = useCallback(
    async (taskId: string, targetStatus: TaskStatus, force = false) => {
      const currentTask = tasks.find((tk) => tk.task_id === taskId);
      const previousStatus = currentTask?.status;

      if (previousStatus && previousStatus !== targetStatus) {
        pendingUserWrites.current.set(taskId, { targetStatus, previousStatus, ts: Date.now() });
        setTasks((prev) => prev.map((tk) => (tk.task_id === taskId ? { ...tk, status: targetStatus } : tk)));
      }

      try {
        await moveTask(taskId, targetStatus, { force });
        pendingUserWrites.current.delete(taskId);
        await fetchTasks();
      } catch (err) {
        pendingUserWrites.current.delete(taskId);
        if (previousStatus) {
          setTasks((prev) => prev.map((tk) => (tk.task_id === taskId ? { ...tk, status: previousStatus } : tk)));
        }
        if (err instanceof ApiError && err.businessCode === 'deps_unmet') {
          const parents = (err.data?.unmet_parents ?? []) as Array<{ task_id: string; title: string; status: string }>;
          const parentTitles = parents.map((p) => `${p.title} (${p.status})`);
          setForcePromoteState({ taskId, targetStatus, parentTitles });
          return;
        }
        toast.error(err instanceof ApiError ? err.message : t('moveError'));
      }
    },
    [tasks, fetchTasks, t],
  );

  const handleForcePromoteConfirm = useCallback(async () => {
    if (!forcePromoteState) return;
    const { taskId, targetStatus } = forcePromoteState;
    setForcePromoteState(null);
    await handleMoveTask(taskId, targetStatus, true);
  }, [forcePromoteState, handleMoveTask]);

  const handleReclaimTask = useCallback(
    async (taskId: string) => {
      try {
        await reclaimTask(taskId);
        await fetchTasks();
        toast.success(t('reclaimSuccess'));
      } catch {
        toast.error(t('reclaimFailed'));
      }
    },
    [fetchTasks, t],
  );

  const handleDeleteTask = useCallback(
    async (taskId: string) => {
      try {
        await deleteTask(taskId);
        await fetchTasks();
        toast.success(t('taskDeleted'));
      } catch {
        toast.error(t('deleteError'));
      }
    },
    [fetchTasks, t],
  );

  const handleBulkMove = useCallback(
    async (taskIds: string[], targetStatus: TaskStatus) => {
      for (const id of taskIds) {
        await handleMoveTask(id, targetStatus);
      }
    },
    [handleMoveTask],
  );

  const {
    sensors,
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
  } = useKanbanDnD({ tasks, selectedTaskIds, onMoveTask: handleMoveTask, onBulkMove: handleBulkMove });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="p-1.5 rounded-full hover:bg-muted transition-colors text-sm">
            &larr;
          </button>
          <div>
            <h2 className="text-base font-semibold">{board.name}</h2>
            {board.description && <p className="text-xs text-muted-foreground mt-0.5">{board.description}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPipelineWizardOpen(true)}
            className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary hover:bg-primary/20 transition-colors inline-flex items-center gap-1"
            title={t('pipelineFromTemplateHint')}
          >
            <Layers className="w-3 h-3" />
            {t('pipelineFromTemplate')}
          </button>
          {triageCount > 0 && (
            <button
              onClick={handleSpecifyAll}
              disabled={specifyAllLoading}
              className="text-xs px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
              title={t('specifyAllHint')}
            >
              {specifyAllLoading ? (
                <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" />
              ) : (
                <Sparkles className="w-3 h-3" />
              )}
              {t('specifyAll', { count: triageCount })}
            </button>
          )}
          <button
            onClick={toggleLaneByProfile}
            className={cn(
              'text-xs px-2.5 py-1 rounded-full transition-colors inline-flex items-center gap-1',
              laneByProfile
                ? 'bg-chart-4/10 text-chart-4 hover:bg-chart-4/20'
                : 'hover:bg-muted text-muted-foreground hover:text-foreground',
            )}
            title={t('laneByProfileHint')}
          >
            <Users className="w-3 h-3" />
            {t('laneByProfile')}
          </button>
          <button
            onClick={() => {
              fetchTasks();
              fetchSummary();
              fetchEdges();
            }}
            className="text-xs px-2.5 py-1 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title={t('refresh')}
          >
            {t('refresh')}
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex gap-3 text-xs text-muted-foreground flex-wrap">
        {STATUS_COLUMNS.map((status) => (
          <span key={status} className="flex items-center gap-1">
            <span className={cn('w-1.5 h-1.5 rounded-full', STATUS_DOT_COLORS[status])} />
            {t(`status.${status}`)}: {summary[status] || 0}
          </span>
        ))}
        {summaryData?.oldest_ready_age_seconds != null && summaryData.oldest_ready_age_seconds >= 300 && (
          <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            {t('oldestReadyAge', { minutes: Math.floor(summaryData.oldest_ready_age_seconds / 60) })}
          </span>
        )}
      </div>

      {/* Per-agent distribution */}
      {summaryData && summaryData.by_agent.length > 1 && (
        <div className="flex gap-2 text-[10px] text-muted-foreground flex-wrap items-center">
          <span className="font-medium">{t('agentDistribution')}:</span>
          {summaryData.by_agent.map((ag) => (
            <span
              key={ag.agent_id ?? '__unassigned__'}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-muted/50"
            >
              <span className="max-w-[100px] truncate">
                {ag.agent_id ? (agentNameMap.get(ag.agent_id) ?? ag.agent_id) : t('unassigned')}
              </span>
              <span className="text-foreground font-medium">{ag.total}</span>
            </span>
          ))}
        </div>
      )}

      {/* View tabs */}
      <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'board' | 'graph' | 'activity')}>
        <TabsList className="h-8">
          <TabsTrigger value="board" className="text-xs px-3 py-1">
            {t('viewBoard')}
          </TabsTrigger>
          <TabsTrigger value="graph" className="text-xs px-3 py-1">
            {t('viewGraph')}
          </TabsTrigger>
          <TabsTrigger value="activity" className="text-xs px-3 py-1">
            {t('viewActivity')}
          </TabsTrigger>
        </TabsList>

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
                    onMoveTask={handleMoveTask}
                    onDeleteTask={handleDeleteTask}
                    onReclaimTask={handleReclaimTask}
                    onRefresh={fetchTasks}
                    laneByProfile={laneByProfile}
                    agentNameMap={agentNameMap}
                    collapsedAgents={collapsedAgents}
                    onToggleAgentCollapse={toggleAgentCollapse}
                    footer={
                      status === 'triage' || status === 'ready' ? (
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
                              skills={newTaskSkills}
                              maxRuntimeSeconds={newTaskMaxRuntime}
                              branch={newTaskBranch}
                              agents={agents}
                              allTasks={tasks}
                              attachments={newTaskAttachments}
                              onAttachmentsChange={setNewTaskAttachments}
                              onTitleChange={setNewTaskTitle}
                              onDescriptionChange={setNewTaskDesc}
                              onSelectedDepsToggle={toggleDep}
                              onShowDepPickerToggle={() => setShowDepPicker((v) => !v)}
                              onShowCriteriaToggle={() => setShowCriteria((v) => !v)}
                              onCriteriaChange={setNewTaskCriteria}
                              onAgentIdChange={setNewTaskAgentId}
                              onSkillsChange={setNewTaskSkills}
                              onMaxRuntimeChange={setNewTaskMaxRuntime}
                              onBranchChange={setNewTaskBranch}
                              onSubmit={handleAddTask}
                              onCancel={resetAddForm}
                            />
                          ) : (
                            <button
                              onClick={() => setAddingColumn(status)}
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
                      ) : undefined
                    }
                    t={t}
                  />
                ))}
              </div>
              <DragOverlay dropAnimation={null}>
                {draggedTaskId ? (
                  <div className="rounded-md shadow-lg scale-105 rotate-1 opacity-90 pointer-events-none max-w-[280px]">
                    {isBulkDrag && (
                      <div className="absolute -top-2 -right-2 z-20 w-5 h-5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center shadow">
                        {selectedTaskIds.length}
                      </div>
                    )}
                    <KanbanTaskCard
                      task={tasks.find((tk) => tk.task_id === draggedTaskId)!}
                      allTasks={tasks}
                      onMove={handleMoveTask}
                      onDelete={handleDeleteTask}
                      onRefresh={fetchTasks}
                      onReclaim={handleReclaimTask}
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
          if (!open) setDrawerTaskId(null);
        }}
        onRefresh={fetchTasks}
        onNavigateTask={setDrawerTaskId}
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

      <KanbanBulkActionBar
        boardId={board.board_id}
        selectedIds={selectedTaskIds}
        onClear={() => setSelectedTaskIds([])}
        onComplete={() => {
          fetchTasks();
          fetchSummary();
        }}
        agents={agents.map((ag) => ({ id: ag.id, name: ag.name }))}
      />

      <ConfirmDialog
        open={!!forcePromoteState}
        onOpenChange={(open) => {
          if (!open) setForcePromoteState(null);
        }}
        title={t('forcePromoteTitle')}
        description={
          forcePromoteState
            ? `${t('forcePromoteDesc')}\n${forcePromoteState.parentTitles.map((p) => `• ${p}`).join('\n')}`
            : ''
        }
        confirmText={t('forcePromoteConfirm')}
        cancelText={t('cancel')}
        variant="warning"
        onConfirm={handleForcePromoteConfirm}
      />

      <ConfirmDialog
        open={!!dropConfirmState}
        onOpenChange={(open) => {
          if (!open) dismissDropConfirm();
        }}
        title={t('dropConfirmTitle')}
        description={
          dropConfirmState ? t('dropConfirmDesc', { status: t(`status.${dropConfirmState.targetStatus}`) }) : ''
        }
        confirmText={t('dropConfirmConfirm')}
        cancelText={t('cancel')}
        variant="destructive"
        onConfirm={handleDropConfirm}
      />
    </div>
  );
}
