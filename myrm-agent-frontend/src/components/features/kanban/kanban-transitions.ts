/**
 * [INPUT]
 * - @/services/kanban::TaskStatus (POS: 看板 API 类型定义)
 * - @shared/config/kanban_move_guard.json (POS: 服务端 move 守卫允许的流转表，前后端共用，由服务端契约测试逐对验证)
 *
 * [OUTPUT]
 * - MoveIntent: 一次「改状态」操作在界面上的真实含义
 * - isServerMoveAllowed: 服务端 move 接口是否接受该起止状态（含「原地不动」）
 * - resolveMoveIntent: 由起止状态判定操作含义
 * - moveLabelKey: 状态流转入口的文案 key
 *
 * [POS]
 * 看板状态流转的单一判定点。卡片菜单、抽屉、拖拽、批量条共用它：服务端必然拒绝的流转在发起前就拦下，
 * 失败 → 就绪走「重试」而不是 move，归档先经过确认。
 */
import type { TaskStatus } from '@/services/kanban';
import moveGuardJson from '@shared/config/kanban_move_guard.json';

/**
 * - move: 普通状态流转，直接调用 move 接口
 * - retry: 失败任务回到就绪，走重试接口（服务端不允许手动 move 出终态）
 * - archive: 归档，先确认
 * - blocked: 服务端必然以 409 拒绝，不应发起
 */
export type MoveIntent = 'move' | 'retry' | 'archive' | 'blocked';

/**
 * 服务端 move 守卫（move_orchestrator.move_task）允许的目标：终态只能归档、草稿池只能去 backlog/ready/archived、审核态不可手动进出。
 * 守卫不特判「原地不动」，所以终态、草稿池、审核态任务移到自己当前的状态同样被拒。
 * 数据在 shared/config/kanban_move_guard.json，服务端契约测试会用真实 move 接口逐对核对它。
 */
const ALLOWED_TARGETS = moveGuardJson as Readonly<Record<TaskStatus, readonly TaskStatus[]>>;

export function isServerMoveAllowed(from: TaskStatus, to: TaskStatus): boolean {
  return ALLOWED_TARGETS[from].includes(to);
}

export function resolveMoveIntent(from: TaskStatus, to: TaskStatus): MoveIntent {
  if (from === to) {
    return 'blocked';
  }
  if (from === 'failed' && to === 'ready') {
    return 'retry';
  }
  if (!isServerMoveAllowed(from, to)) {
    return 'blocked';
  }
  return to === 'archived' ? 'archive' : 'move';
}

/** kanban 命名空间下的文案 key：重试入口显示「重试」，其余沿用「移至 X」。 */
export function moveLabelKey(from: TaskStatus, to: TaskStatus): string {
  return resolveMoveIntent(from, to) === 'retry' ? 'retryAction' : `moveTo.${to}`;
}
