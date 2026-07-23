/**
 * [POS] Subagent tree data utilities. Pure functions for building, aggregating,
 *       sorting, filtering, and formatting subagent tree data.
 * [INPUT] useSubagentStore::SubagentNode, SubagentStatus (POS: Subagent state store)
 * [OUTPUT] buildTree, aggregate, treeTotals, sortNodes, filterNodes, flattenTree, fmtCost, fmtTokens
 */
import type { SubagentNode, SubagentStatus } from '@/store/chat/useSubagentStore';

// ── Types ────────────────────────────────────────────────────────────

export type SortMode = 'spawn' | 'busiest' | 'slowest' | 'status';
export type FilterMode = 'all' | 'running' | 'failed' | 'leaf';

export interface TreeNode extends SubagentNode {
  children: TreeNode[];
}

export interface SubtreeAggregate {
  descendantCount: number;
  totalCostUsd: number;
  totalTokens: number;
  totalDurationSeconds: number;
  activeCount: number;
}

export interface TreeTotals extends SubtreeAggregate {
  totalAgents: number;
  failedCount: number;
  modelMix: { model: string; count: number }[];
}

// ── Build Tree ───────────────────────────────────────────────────────

export function buildTree(nodes: Record<string, SubagentNode>): TreeNode[] {
  const entries = Object.values(nodes);
  if (entries.length === 0) return [];

  const map: Record<string, TreeNode> = {};
  for (const n of entries) {
    map[n.task_id] = { ...n, children: [] };
  }

  const roots: TreeNode[] = [];
  for (const n of entries) {
    if (n.parent_task_id && map[n.parent_task_id]) {
      map[n.parent_task_id].children.push(map[n.task_id]);
    } else {
      roots.push(map[n.task_id]);
    }
  }

  return roots;
}

// ── Aggregate ────────────────────────────────────────────────────────

function extractCostUsd(node: SubagentNode): number {
  const raw = node.budget?.cost_usd;
  if (typeof raw === 'number') return raw;
  if (typeof raw === 'string') {
    const n = Number(raw);
    return Number.isFinite(n) ? n : 0;
  }
  return 0;
}

function extractTotalTokens(node: SubagentNode): number {
  const raw = node.token_usage?.total_tokens;
  return typeof raw === 'number' && raw > 0 ? raw : 0;
}

export function aggregate(node: TreeNode): SubtreeAggregate {
  let descendantCount = 0;
  let totalCostUsd = extractCostUsd(node);
  let totalTokens = extractTotalTokens(node);
  let totalDurationSeconds = node.duration_seconds ?? 0;
  let activeCount = node.status === 'running' ? 1 : 0;

  for (const child of node.children) {
    const childAgg = aggregate(child);
    descendantCount += childAgg.descendantCount + 1;
    totalCostUsd += childAgg.totalCostUsd;
    totalTokens += childAgg.totalTokens;
    totalDurationSeconds += childAgg.totalDurationSeconds;
    activeCount += childAgg.activeCount;
  }

  return { descendantCount, totalCostUsd, totalTokens, totalDurationSeconds, activeCount };
}

// ── Tree Totals ──────────────────────────────────────────────────────

const FAILED_STATUSES = new Set<SubagentStatus>([
  'failed', 'timed_out', 'interrupted',
]);

export function treeTotals(roots: TreeNode[]): TreeTotals {
  const modelCounts: Record<string, number> = {};
  let totalAgents = 0;
  let failedCount = 0;
  let totalCostUsd = 0;
  let totalTokens = 0;
  let totalDurationSeconds = 0;
  let activeCount = 0;

  const walk = (nodes: TreeNode[]) => {
    for (const n of nodes) {
      totalAgents++;
      if (FAILED_STATUSES.has(n.status)) failedCount++;
      if (n.status === 'running') activeCount++;
      totalCostUsd += extractCostUsd(n);
      totalTokens += extractTotalTokens(n);
      totalDurationSeconds += n.duration_seconds ?? 0;
      const model = n.effective_model?.split('/').pop() ?? '';
      if (model) modelCounts[model] = (modelCounts[model] ?? 0) + 1;
      walk(n.children);
    }
  };

  walk(roots);

  const modelMix = Object.entries(modelCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([model, count]) => ({ model, count }));

  return {
    totalAgents,
    failedCount,
    descendantCount: totalAgents,
    totalCostUsd,
    totalTokens,
    totalDurationSeconds,
    activeCount,
    modelMix,
  };
}

// ── Sort ──────────────────────────────────────────────────────────────

const STATUS_RANK: Record<string, number> = {
  failed: 0,
  timed_out: 0,
  interrupted: 1,
  running: 2,
  verifying: 2,
  pending: 3,
  pending_approval: 3,
  yielded: 3,
  completed: 4,
  cancelled: 5,
  cancelled_by_budget: 5,
  checkpoint: 6,
};

function sortComparator(mode: SortMode): (a: TreeNode, b: TreeNode) => number {
  switch (mode) {
    case 'busiest':
      return (a, b) => {
        const aCost = extractCostUsd(a);
        const bCost = extractCostUsd(b);
        if (aCost !== bCost) return bCost - aCost;
        return extractTotalTokens(b) - extractTotalTokens(a);
      };
    case 'slowest':
      return (a, b) => (b.duration_seconds ?? 0) - (a.duration_seconds ?? 0);
    case 'status':
      return (a, b) => (STATUS_RANK[a.status] ?? 99) - (STATUS_RANK[b.status] ?? 99);
    default:
      return () => 0;
  }
}

export function sortNodes(nodes: TreeNode[], mode: SortMode): TreeNode[] {
  if (mode === 'spawn') return nodes;
  return [...nodes].sort(sortComparator(mode));
}

// ── Filter ───────────────────────────────────────────────────────────

export function filterNodes(nodes: TreeNode[], mode: FilterMode): TreeNode[] {
  if (mode === 'all') return nodes;

  const flat = flattenTree(nodes);
  const strip = (n: TreeNode): TreeNode => ({ ...n, children: [] });
  switch (mode) {
    case 'running':
      return flat.filter(n => n.status === 'running' || n.status === 'verifying').map(strip);
    case 'failed':
      return flat.filter(n => FAILED_STATUSES.has(n.status)).map(strip);
    case 'leaf':
      return flat.filter(n => n.children.length === 0).map(strip);
    default:
      return nodes;
  }
}

// ── Flatten ──────────────────────────────────────────────────────────

export function flattenTree(nodes: TreeNode[]): TreeNode[] {
  const result: TreeNode[] = [];
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      result.push(n);
      walk(n.children);
    }
  };
  walk(nodes);
  return result;
}

// ── Format ───────────────────────────────────────────────────────────

export function fmtCost(usd: number): string {
  if (!Number.isFinite(usd) || usd <= 0) return '';
  if (usd < 0.01) return '<$0.01';
  if (usd < 10) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(1)}`;
}

export function fmtTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0';
  if (n < 1000) return String(Math.round(n));
  if (n < 10_000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}
