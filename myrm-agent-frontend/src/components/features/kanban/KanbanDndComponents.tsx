/**
 * [INPUT]
 * - @dnd-kit/core::useDroppable, useDraggable (POS: 跨平台拖拽基础设施)
 * - ./KanbanTaskCard (POS: 看板任务卡片渲染组件)
 *
 * [OUTPUT]
 * - KanbanDropColumn: 可放置的看板列组件（集成 useDroppable + 高亮/占位符动画）
 * - DraggableTaskCard: 可拖拽的任务卡片包装器（集成 useDraggable + 多选标记）
 *
 * [POS]
 * 看板 DnD 渲染组件层。提供列级 drop target、卡片级 drag source 的 UI 封装，以及 Running 列按 Agent 分泳道渲染。
 */
'use client';

import { useMemo } from 'react';
import { useDroppable, useDraggable } from '@dnd-kit/core';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import KanbanTaskCard from './KanbanTaskCard';

const STATUS_STYLES: Record<TaskStatus, string> = {
  triage: 'bg-purple-500/5 border-purple-500/30',
  backlog: 'bg-muted/50 border-muted-foreground/20',
  ready: 'bg-primary/5 border-primary/30',
  running: 'bg-chart-4/10 border-chart-4/40',
  blocked: 'bg-destructive/5 border-destructive/30',
  completed: 'bg-chart-2/10 border-chart-2/40',
  failed: 'bg-destructive/10 border-destructive/40',
  archived: 'bg-muted/30 border-muted-foreground/10',
};

interface KanbanDropColumnProps {
  status: TaskStatus;
  tasks: KanbanTask[];
  allTasks: KanbanTask[];
  draggedTaskId: string | null;
  dragOverColumn: TaskStatus | null;
  selectedTaskIds: string[];
  onTaskSelect: (taskId: string, e: React.MouseEvent) => void;
  onMoveTask: (taskId: string, targetStatus: TaskStatus) => void;
  onDeleteTask: (taskId: string) => void;
  onReclaimTask: (taskId: string) => void;
  onRefresh: () => void;
  laneByProfile?: boolean;
  agentNameMap?: Map<string, string>;
  collapsedAgents?: Set<string>;
  onToggleAgentCollapse?: (agentKey: string) => void;
  footer?: React.ReactNode;
  t: ReturnType<typeof useTranslations<'kanban'>>;
}

export function KanbanDropColumn({
  status,
  tasks: columnTaskItems,
  allTasks,
  draggedTaskId,
  dragOverColumn,
  selectedTaskIds,
  onTaskSelect,
  onMoveTask,
  onDeleteTask,
  onReclaimTask,
  onRefresh,
  laneByProfile,
  agentNameMap,
  collapsedAgents,
  onToggleAgentCollapse,
  footer,
  t,
}: KanbanDropColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const isHighlighted = (isOver || dragOverColumn === status) && draggedTaskId !== null;

  const agentLanes = useMemo(() => {
    if (!laneByProfile || status !== 'running') return null;
    const groups = new Map<string | null, KanbanTask[]>();
    for (const task of columnTaskItems) {
      const key = task.agent_id ?? null;
      const arr = groups.get(key);
      if (arr) arr.push(task);
      else groups.set(key, [task]);
    }
    return [...groups.entries()].sort(([a], [b]) => {
      if (a === null) return 1;
      if (b === null) return -1;
      const nameA = agentNameMap?.get(a) ?? a;
      const nameB = agentNameMap?.get(b) ?? b;
      return nameA.localeCompare(nameB);
    });
  }, [columnTaskItems, laneByProfile, status, agentNameMap]);

  const showLaneHeaders = agentLanes !== null && agentLanes.length > 1;

  const renderTaskCards = (items: KanbanTask[]) =>
    items.map((task) => (
      <DraggableTaskCard
        key={task.task_id}
        task={task}
        allTasks={allTasks}
        draggedTaskId={draggedTaskId}
        selectedTaskIds={selectedTaskIds}
        onTaskSelect={onTaskSelect}
        onMoveTask={onMoveTask}
        onDeleteTask={onDeleteTask}
        onReclaimTask={onReclaimTask}
        onRefresh={onRefresh}
      />
    ));

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex-1 min-w-[220px] max-w-[300px] rounded-lg border p-3 flex flex-col gap-2 transition-all duration-200',
        STATUS_STYLES[status],
        isHighlighted && 'ring-2 ring-primary/50 scale-[1.01] border-primary/50',
      )}
    >
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t(`status.${status}`)}</h3>
        <span className="text-xs text-muted-foreground">{columnTaskItems.length}</span>
      </div>

      <div className="flex-1 space-y-2 min-h-[60px]">
        {isHighlighted && (
          <div className="h-12 rounded-md border-2 border-dashed border-primary/40 bg-primary/5 flex items-center justify-center transition-all duration-200 animate-in fade-in-0 zoom-in-95">
            <span className="text-[10px] text-primary/60 font-medium">{t('dropHere')}</span>
          </div>
        )}
        {showLaneHeaders
          ? agentLanes.map(([agentId, laneTasks]) => {
              const laneKey = agentId ?? '__unassigned__';
              const isCollapsed = collapsedAgents?.has(laneKey) ?? false;
              const displayName = agentId ? (agentNameMap?.get(agentId) ?? agentId) : t('unassigned');
              return (
                <div key={laneKey}>
                  <button
                    onClick={() => onToggleAgentCollapse?.(laneKey)}
                    className="w-full flex items-center gap-1.5 py-1 border-b border-dashed border-muted-foreground/20 mb-1.5 group/lane"
                  >
                    {isCollapsed ? (
                      <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
                    )}
                    <span
                      className={cn(
                        'text-[10px] font-medium truncate',
                        agentId ? 'text-chart-4' : 'text-muted-foreground italic',
                      )}
                    >
                      {displayName}
                    </span>
                    <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                      {t('tasksInLane', { count: laneTasks.length })}
                    </span>
                  </button>
                  {!isCollapsed && <div className="space-y-2 pl-1">{renderTaskCards(laneTasks)}</div>}
                </div>
              );
            })
          : renderTaskCards(columnTaskItems)}
      </div>

      {footer}
    </div>
  );
}

interface DraggableTaskCardProps {
  task: KanbanTask;
  allTasks: KanbanTask[];
  draggedTaskId: string | null;
  selectedTaskIds: string[];
  onTaskSelect: (taskId: string, e: React.MouseEvent) => void;
  onMoveTask: (taskId: string, targetStatus: TaskStatus) => void;
  onDeleteTask: (taskId: string) => void;
  onReclaimTask: (taskId: string) => void;
  onRefresh: () => void;
}

function DraggableTaskCard({
  task,
  allTasks,
  draggedTaskId,
  selectedTaskIds,
  onTaskSelect,
  onMoveTask,
  onDeleteTask,
  onReclaimTask,
  onRefresh,
}: DraggableTaskCardProps) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: task.task_id });

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onClick={(e) => {
        if (e.ctrlKey || e.metaKey || e.shiftKey) {
          e.preventDefault();
          e.stopPropagation();
          onTaskSelect(task.task_id, e);
        }
      }}
      className={cn(
        'relative rounded-md transition-all cursor-grab active:cursor-grabbing touch-none',
        selectedTaskIds.includes(task.task_id) && 'ring-2 ring-primary/60 ring-offset-1',
        (isDragging || draggedTaskId === task.task_id) && 'opacity-40 scale-95',
      )}
    >
      {selectedTaskIds.includes(task.task_id) && (
        <div className="absolute -top-1 -left-1 z-10 w-4 h-4 rounded-full bg-primary flex items-center justify-center">
          <svg
            className="w-2.5 h-2.5 text-primary-foreground"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
      )}
      <KanbanTaskCard
        task={task}
        allTasks={allTasks}
        onMove={onMoveTask}
        onDelete={onDeleteTask}
        onRefresh={onRefresh}
        onReclaim={onReclaimTask}
      />
    </div>
  );
}
