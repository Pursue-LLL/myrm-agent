/**
 * [INPUT]
 * - @/services/kanban::KanbanTask, TaskStatus (POS: 看板 API 类型定义)
 *
 * [OUTPUT]
 * - UNASSIGNED_LANE_KEY: 「未指派」泳道在折叠集合里的 key
 * - groupTasksIntoLanes: 把任务按 Agent 分组并排序
 * - columnLanes: 一列此刻是否按泳道渲染，是则给出泳道
 * - visibleColumnTasks: 一列里用户此刻看得见的卡片，按屏幕上的顺序
 * - TaskClickContext / applyTaskClick: 一次卡片点选（单点切换 / Shift 区间）之后的选中集合
 *
 * [POS]
 * 看板多选的纯逻辑层。Shift 区间只在锚点所在的列内、按屏幕上实际显示的顺序取，
 * 与列渲染共用同一套泳道规则，所以用户看不见的卡片（别的列、被过滤、被折叠的泳道）不会被选中。
 */
import type { KanbanTask, TaskStatus } from '@/services/kanban';

/** 只有 Running 列会按 Agent 分泳道。 */
const LANE_STATUS: TaskStatus = 'running';

export const UNASSIGNED_LANE_KEY = '__unassigned__';

export type TaskLane = readonly [agentId: string | null, tasks: KanbanTask[]];

export interface LaneOptions {
  laneByProfile: boolean;
  agentNameMap?: ReadonlyMap<string, string>;
  collapsedAgents?: ReadonlySet<string>;
}

export interface TaskClickContext extends LaneOptions {
  /** 当前看板的全部任务，用来查被点任务所在的列。 */
  tasks: readonly KanbanTask[];
  /** 经过责任人筛选后每列实际展示的任务。 */
  columnTasks: Readonly<Record<TaskStatus, readonly KanbanTask[]>>;
}

export function laneKeyOf(agentId: string | null): string {
  return agentId ?? UNASSIGNED_LANE_KEY;
}

/** 按 Agent 名称排序，未指派排最后；同一泳道内保持传入顺序。 */
export function groupTasksIntoLanes(
  tasks: readonly KanbanTask[],
  agentNameMap?: ReadonlyMap<string, string>,
): TaskLane[] {
  const groups = new Map<string | null, KanbanTask[]>();
  for (const task of tasks) {
    const key = task.agent_id ?? null;
    const group = groups.get(key);
    if (group) {
      group.push(task);
    } else {
      groups.set(key, [task]);
    }
  }
  return [...groups.entries()].sort(([a], [b]) => {
    if (a === null) {
      return 1;
    }
    if (b === null) {
      return -1;
    }
    return (agentNameMap?.get(a) ?? a).localeCompare(agentNameMap?.get(b) ?? b);
  });
}

/** 只有 Running 列且至少两个泳道时才会画泳道标题；其余情况整列按原顺序平铺，返回 null。 */
export function columnLanes(
  status: TaskStatus,
  tasks: readonly KanbanTask[],
  { laneByProfile, agentNameMap }: LaneOptions,
): TaskLane[] | null {
  if (!laneByProfile || status !== LANE_STATUS) {
    return null;
  }
  const lanes = groupTasksIntoLanes(tasks, agentNameMap);
  return lanes.length > 1 ? lanes : null;
}

/** 用户在这一列里此刻看得见的卡片，顺序与屏幕一致：折叠的泳道不显示它的卡片。 */
export function visibleColumnTasks(
  status: TaskStatus,
  tasks: readonly KanbanTask[],
  options: LaneOptions,
): readonly KanbanTask[] {
  const lanes = columnLanes(status, tasks, options);
  if (!lanes) {
    return tasks;
  }
  return lanes
    .filter(([agentId]) => !options.collapsedAgents?.has(laneKeyOf(agentId)))
    .flatMap(([, laneTasks]) => laneTasks);
}

/**
 * 一次卡片点选后的选中集合。`extendRange` 为 true 时从最后一次选中的卡片（锚点）选到被点的卡片；
 * 锚点不在同一列或已不可见时，退化为单卡切换，避免选到用户看不到的任务。
 */
export function applyTaskClick(
  selected: readonly string[],
  { taskId, extendRange }: { taskId: string; extendRange: boolean },
  context: TaskClickContext,
): string[] {
  const toggled = selected.includes(taskId) ? selected.filter((id) => id !== taskId) : [...selected, taskId];
  if (!extendRange || selected.length === 0) {
    return toggled;
  }
  const status = context.tasks.find((task) => task.task_id === taskId)?.status;
  if (!status) {
    return toggled;
  }
  const shown = visibleColumnTasks(status, context.columnTasks[status], context).map((task) => task.task_id);
  const anchorIndex = shown.indexOf(selected[selected.length - 1]);
  const clickedIndex = shown.indexOf(taskId);
  if (anchorIndex < 0 || clickedIndex < 0) {
    return toggled;
  }
  const from = Math.min(anchorIndex, clickedIndex);
  const to = Math.max(anchorIndex, clickedIndex);
  return [...new Set([...selected, ...shown.slice(from, to + 1)])];
}
