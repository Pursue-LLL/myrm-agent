/**
 * [INPUT]
 * - @dnd-kit/core::useDroppable, useDraggable (POS: 跨平台拖拽基础设施)
 * - ./KanbanTaskCard (POS: 看板任务卡片渲染组件)
 * - ./kanban-card-gestures::ISOLATE_FROM_CARD (POS: 卡片内控件的手势隔离，勾选框展开它)
 * - @/components/primitives/checkbox (POS: Radix 勾选框封装)
 * - ./kanban-selection::columnLanes, laneKeyOf (POS: 看板多选与泳道规则，列渲染与 Shift 区间共用)
 *
 * [OUTPUT]
 * - KanbanDropColumn: 可放置的看板列组件（集成 useDroppable + 高亮/占位符动画）
 * - DraggableTaskCard: 可拖拽的任务卡片包装器（集成 useDraggable + 多选勾选框 + 双击/附件入口开 Drawer）
 *
 * [POS]
 * 看板 DnD 渲染组件层。提供列级 drop target、卡片级 drag source 的 UI 封装，以及 Running 列按 Agent 分泳道渲染。
 */
'use client';

import { useCallback, useMemo } from 'react';
import { useDroppable, useDraggable } from '@dnd-kit/core';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Checkbox } from '@/components/primitives/checkbox';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import KanbanTaskCard from './KanbanTaskCard';
import { ISOLATE_FROM_CARD } from './kanban-card-gestures';
import { columnLanes, laneKeyOf } from './kanban-selection';

/**
 * 勾选框的显现契约（悬停 / 键盘聚焦 / 触屏三路径），与 `REVEAL_ON_HOVER` 同构；卡片内部已有无名 `group`，
 * 所以挂在卡片包装层的命名组 `group/select` 上，命名组无法复用常量，需就地写出完整类名。
 */
const SELECT_REVEAL =
  'opacity-0 group-hover/select:opacity-100 group-focus-within/select:opacity-100 pointer-coarse:opacity-100';

const STATUS_STYLES: Record<TaskStatus, string> = {
  triage: 'bg-purple-500/5 border-purple-500/30',
  backlog: 'bg-muted/50 border-muted-foreground/20',
  ready: 'bg-primary/5 border-primary/30',
  running: 'bg-chart-4/10 border-chart-4/40',
  blocked: 'bg-destructive/5 border-destructive/30',
  in_review: 'bg-amber-500/5 border-amber-500/30',
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
  onOpenTaskDrawer?: (taskId: string) => void;
  laneByProfile?: boolean;
  agentNameMap?: Map<string, string>;
  collapsedAgents?: Set<string>;
  onToggleAgentCollapse?: (agentKey: string) => void;
  footer?: React.ReactNode;
  queuedByConcurrency?: boolean;
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
  onOpenTaskDrawer,
  laneByProfile,
  agentNameMap,
  collapsedAgents,
  onToggleAgentCollapse,
  footer,
  queuedByConcurrency,
  t,
}: KanbanDropColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: status,
    disabled: status === 'in_review',
  });
  const isHighlighted = (isOver || dragOverColumn === status) && draggedTaskId !== null;

  const agentLanes = useMemo(
    () => columnLanes(status, columnTaskItems, { laneByProfile: !!laneByProfile, agentNameMap }),
    [status, columnTaskItems, laneByProfile, agentNameMap],
  );

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
        onOpenTaskDrawer={onOpenTaskDrawer}
        queuedByConcurrency={queuedByConcurrency}
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
        {agentLanes
          ? agentLanes.map(([agentId, laneTasks]) => {
              const laneKey = laneKeyOf(agentId);
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
  onOpenTaskDrawer?: (taskId: string) => void;
  queuedByConcurrency?: boolean;
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
  onOpenTaskDrawer,
  queuedByConcurrency = false,
}: DraggableTaskCardProps) {
  const t = useTranslations('kanban');
  const selected = selectedTaskIds.includes(task.task_id);
  const selecting = selectedTaskIds.length > 0;
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } = useDraggable({
    id: task.task_id,
    disabled: task.status === 'in_review',
  });
  // dnd-kit 的键盘激活只在登记了 activator 时才校验 event.target；未登记时卡片内任何按钮上的
  // Enter/Space 都会被当作“开始拖拽”并 preventDefault，卡片里的菜单与展开按钮就无法用键盘操作。
  // 把卡片自身登记为 activator，拖拽仍可由聚焦卡片后按 Space/Enter 触发。
  const setCardRef = useCallback(
    (node: HTMLElement | null) => {
      setNodeRef(node);
      setActivatorNodeRef(node);
    },
    [setNodeRef, setActivatorNodeRef],
  );

  return (
    // oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- role, tabIndex and key listeners come from dnd-kit via spread
    <div
      ref={setCardRef}
      {...listeners}
      {...attributes}
      onClick={(e) => {
        if (e.ctrlKey || e.metaKey || e.shiftKey) {
          e.preventDefault();
          e.stopPropagation();
          onTaskSelect(task.task_id, e);
        }
      }}
      onDoubleClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onOpenTaskDrawer?.(task.task_id);
      }}
      title={onOpenTaskDrawer ? t('openDetailsHint') : undefined}
      className={cn(
        // 触屏平移留给浏览器：从卡片上起手的滑动用来滚动看板，只有长按才由 TouchSensor 起拖拽。
        // 圆角与卡片本体一致，选中描边和拖拽缩放才贴合卡片轮廓。
        'group/select relative rounded-lg transition-all touch-manipulation',
        task.status !== 'in_review' && 'cursor-grab active:cursor-grabbing',
        selected && 'ring-2 ring-primary/60 ring-offset-1',
        (isDragging || draggedTaskId === task.task_id) && 'opacity-40 scale-95',
      )}
    >
      <Checkbox
        checked={selected}
        aria-label={t('selectTask', { title: task.title })}
        {...ISOLATE_FROM_CARD}
        // 点击自己处理选择，同样先截断冒泡（与隔离属性里的 onClick 等效，这里取代它）。
        onClick={(e) => {
          e.stopPropagation();
          onTaskSelect(task.task_id, e);
        }}
        className={cn(
          // globals.css 的 `* { border-color }` 不在 layer 内，会盖掉普通的 border 色类，描边色必须加 `!` 才生效；
          // 描边用完整主色，未选中的圆圈在深浅两套主题下才与卡片底色保持 3:1 以上的对比度。
          'absolute -top-1.5 -left-1.5 z-10 size-[18px] rounded-full !border-primary bg-background shadow-sm',
          'after:absolute after:-inset-1.5 after:content-[""] [&_svg]:size-3',
          'data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground',
          'pointer-coarse:size-6',
          // 选择模式（已有选中项）下所有卡片都常显勾选框，才能继续点选；平时仅悬停 / 聚焦 / 触屏显现。
          'transition-opacity',
          selecting ? 'opacity-100' : SELECT_REVEAL,
        )}
      />
      <KanbanTaskCard
        task={task}
        allTasks={allTasks}
        onMove={onMoveTask}
        onDelete={onDeleteTask}
        onRefresh={onRefresh}
        onReclaim={onReclaimTask}
        onOpenTaskDrawer={onOpenTaskDrawer}
        queuedByConcurrency={queuedByConcurrency}
      />
    </div>
  );
}
