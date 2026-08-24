/**
 * [POS] Stage task count & upstream dependency derivation.
 *       Computes fine-grained (Scope / Fan-out / Verify / Synthesize) stage progress
 *       metrics from subagent tree nodes, including done/total ratios and upstream blocker indications.
 * [INPUT] useSubagentStore::SubagentNode, TreeNode
 * [OUTPUT] StageProgressItem, StageTaskCountSummary, deriveStageTaskCounts
 */
import type { SubagentNode, SubagentStatus } from '@/store/chat/useSubagentStore';

export type StageCategory = 'scope' | 'fan_out' | 'verify' | 'synthesize' | 'custom';

export interface StageProgressItem {
  id: string;
  category: StageCategory;
  name: string;
  completed: number;
  total: number;
  running: number;
  failed: number;
  waitingOnStage?: string;
  isBlocked: boolean;
  isComplete: boolean;
}

export interface StageTaskCountSummary {
  stages: StageProgressItem[];
  totalTasks: number;
  totalCompleted: number;
  hasBlockers: boolean;
}

const TERMINAL_STATUSES: ReadonlySet<SubagentStatus> = new Set<SubagentStatus>([
  'completed',
  'failed',
  'timed_out',
  'cancelled',
  'cancelled_by_budget',
  'interrupted',
]);

/**
 * Classifies an agent type or role or description into a standardized workflow stage category.
 */
export function classifyNodeStage(node: SubagentNode): { category: StageCategory; name: string } {
  const typeLower = (node.agent_type || '').toLowerCase();
  const descLower = (node.description || '').toLowerCase();
  const roleLower = (node.role || '').toLowerCase();

  let res: { category: StageCategory; name: string };
  if (
    typeLower.includes('scope') ||
    typeLower.includes('plan') ||
    roleLower.includes('scope') ||
    descLower.startsWith('scope') ||
    descLower.startsWith('plan')
  ) {
    res = { category: 'scope', name: 'Scope' };
  } else if (
    typeLower.includes('verif') ||
    typeLower.includes('audit') ||
    typeLower.includes('review') ||
    roleLower.includes('verif') ||
    roleLower.includes('auditor') ||
    Boolean(node.verification) ||
    node.status === 'verifying'
  ) {
    res = { category: 'verify', name: 'Verify' };
  } else if (
    typeLower.includes('synthesize') ||
    typeLower.includes('summary') ||
    typeLower.includes('merge') ||
    typeLower.includes('report') ||
    roleLower.includes('synthesize') ||
    descLower.startsWith('synthesize')
  ) {
    res = { category: 'synthesize', name: 'Synthesize' };
  } else if (
    typeLower.includes('worker') ||
    typeLower.includes('fission') ||
    typeLower.includes('exec') ||
    typeLower.includes('coder') ||
    typeLower.includes('scout') ||
    typeLower.includes('researcher') ||
    node.parent_task_id
  ) {
    res = { category: 'fan_out', name: 'Fan-out' };
  } else {
    res = { category: 'custom', name: node.agent_type || 'Task' };
  }
  return res;
}

/**
 * Derives stage-level task metrics and upstream dependency waiting status.
 * e.g., Scope 1/1 · Fan-out 18/18 · Verify 11/18 · Synthesize 0/1 waiting on verify
 */
export function deriveStageTaskCounts(nodes: Record<string, SubagentNode> | SubagentNode[]): StageTaskCountSummary {
  const nodeList = Array.isArray(nodes) ? nodes : Object.values(nodes);
  const visibleNodes = nodeList.filter((n) => !n.internal);

  if (visibleNodes.length === 0) {
    return {
      stages: [],
      totalTasks: 0,
      totalCompleted: 0,
      hasBlockers: false,
    };
  }

  const stageBuckets = new Map<string, { category: StageCategory; name: string; nodes: SubagentNode[] }>();

  // Canonical ordering of stages
  const STAGE_ORDER: StageCategory[] = ['scope', 'fan_out', 'verify', 'synthesize', 'custom'];

  for (const node of visibleNodes) {
    const { category, name } = classifyNodeStage(node);
    const key = `${category}:${name}`;
    if (!stageBuckets.has(key)) {
      stageBuckets.set(key, { category, name, nodes: [] });
    }
    stageBuckets.get(key)!.nodes.push(node);
  }

  // Sort stages by canonical stage order
  const sortedKeys = Array.from(stageBuckets.keys()).sort((a, b) => {
    const catA = stageBuckets.get(a)!.category;
    const catB = stageBuckets.get(b)!.category;
    const orderA = STAGE_ORDER.indexOf(catA);
    const orderB = STAGE_ORDER.indexOf(catB);
    return orderA - orderB;
  });

  const stages: StageProgressItem[] = [];
  let previousStageIncomplete: string | undefined = undefined;

  for (const key of sortedKeys) {
    const bucket = stageBuckets.get(key)!;
    const total = bucket.nodes.length;
    const completed = bucket.nodes.filter((n) => n.status === 'completed').length;
    const failed = bucket.nodes.filter((n) => n.status === 'failed' || n.status === 'timed_out').length;
    const running = bucket.nodes.filter((n) => n.status === 'running' || n.status === 'verifying').length;
    const isComplete = total > 0 && completed + failed >= total && running === 0;

    let waitingOnStage: string | undefined = undefined;
    let isBlocked = false;

    // If this stage hasn't completed and there is an incomplete upstream stage, note the blocker
    if (!isComplete && previousStageIncomplete && (bucket.category === 'verify' || bucket.category === 'synthesize')) {
      waitingOnStage = previousStageIncomplete;
      isBlocked = true;
    }

    if (!isComplete && !previousStageIncomplete) {
      previousStageIncomplete = bucket.name.toLowerCase();
    }

    stages.push({
      id: key,
      category: bucket.category,
      name: bucket.name,
      completed,
      total,
      running,
      failed,
      waitingOnStage,
      isBlocked,
      isComplete,
    });
  }

  const totalTasks = visibleNodes.length;
  const totalCompleted = visibleNodes.filter((n) => TERMINAL_STATUSES.has(n.status)).length;
  const hasBlockers = stages.some((s) => s.isBlocked);

  return {
    stages,
    totalTasks,
    totalCompleted,
    hasBlockers,
  };
}
