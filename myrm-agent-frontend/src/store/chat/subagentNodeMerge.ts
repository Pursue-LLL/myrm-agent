import type { SubagentNode, SubagentStatus } from './useSubagentStore';

/** Terminal subagent statuses that must not be downgraded by late SSE/API `running` snapshots. */
const TERMINAL_SUBAGENT_STATUSES: ReadonlySet<SubagentStatus> = new Set<SubagentStatus>([
  'completed',
  'failed',
  'timed_out',
  'cancelled',
  'cancelled_by_budget',
  'interrupted',
  'blocked',
]);

/**
 * Folds a server snapshot into the current tree: internal nodes are skipped and snapshot fields win over stored ones.
 */
export function mergeSubagentSnapshot(
  current: Record<string, SubagentNode>,
  snapshot: SubagentNode[],
): Record<string, SubagentNode> {
  const merged = { ...current };
  for (const node of snapshot) {
    if (node.internal) {
      continue;
    }
    const existing = merged[node.task_id];
    // 防回退：本地已是终态（cancelled/completed/failed 等）的节点，
    // 不允许被 SSE/API 迟到的 running 快照覆盖回退——取消后 task 清理
    // 存在窗口，后端可能仍短暂广播 running。
    merged[node.task_id] =
      existing && TERMINAL_SUBAGENT_STATUSES.has(existing.status) && node.status === 'running'
        ? { ...existing, ...node, status: existing.status }
        : { ...existing, ...node };
  }
  return merged;
}
