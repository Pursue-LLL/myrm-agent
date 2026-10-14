/**
 * [INPUT]
 * - @/services/kanban::TaskStatus (POS: 看板 API 类型定义)
 *
 * [OUTPUT]
 * - MoveIntent: 一次「改状态」操作在界面上的真实含义
 * - resolveMoveIntent: 由起止状态判定操作含义（镜像服务端 move 守卫）
 * - moveLabelKey: 状态流转入口的文案 key
 *
 * [POS]
 * 看板状态流转的单一判定点。卡片菜单、抽屉、拖拽共用它：服务端必然拒绝的流转在发起前就拦下，
 * 失败 → 就绪走「重试」而不是 move，归档先经过确认。
 */
import type { TaskStatus } from '@/services/kanban';

/**
 * - move: 普通状态流转，直接调用 move 接口
 * - retry: 失败任务回到就绪，走重试接口（服务端不允许手动 move 出终态）
 * - archive: 归档，先确认
 * - blocked: 服务端必然以 409 拒绝，不应发起
 */
export type MoveIntent = 'move' | 'retry' | 'archive' | 'blocked';

const TERMINAL_STATUSES: readonly TaskStatus[] = ['completed', 'failed', 'archived'];
const TRIAGE_TARGETS: readonly TaskStatus[] = ['backlog', 'ready', 'archived'];

/** 服务端 move 守卫（move_orchestrator.move_task）：终态只能归档、草稿池只能去 backlog/ready/archived、审核态不可手动进出。 */
function isServerMoveAllowed(from: TaskStatus, to: TaskStatus): boolean {
  if (from === 'in_review' || to === 'in_review') {
    return false;
  }
  if (TERMINAL_STATUSES.includes(from)) {
    return to === 'archived';
  }
  if (from === 'triage') {
    return TRIAGE_TARGETS.includes(to);
  }
  return true;
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
