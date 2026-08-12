/**
 * [POS] Task topology model. Pure functions that turn live subagent tree /
 *       fission topology data into a renderable ReactFlow graph model.
 * [INPUT] useSubagentStore::SubagentNode, FissionTopology (POS: Subagent state store)
 * [OUTPUT] buildTopologyModel, buildFissionTopologyModel, buildMergedTopologyModel,
 *       toneForStatus, truncateLabel, TopologyModel, TopologyNodeData, TopologyTone
 */
import type { FissionTopology, SubagentNode } from '@/store/chat/useSubagentStore';
import { extractCostUsd, extractTotalTokens } from './subagentTree';

// ── Types ────────────────────────────────────────────────────────────

/** Semantic tone used to style a topology node (border / icon / pulse). */
export type TopologyTone = 'active' | 'pending' | 'success' | 'danger' | 'warning' | 'muted';

export interface TopologyNodeData {
  taskId: string;
  label: string;
  agentType: string;
  status: string;
  tone: TopologyTone;
  /** 0-100, null when unknown */
  progress: number | null;
  costUsd: number;
  tokens: number;
  durationSeconds: number;
  error?: string;
  parentTaskId?: string;
  /** Fission fallback root marker */
  isRoot?: boolean;
  /** Adversarial verification outcome (present only when the worker was verified) */
  verification?: { passed: boolean };
}

export interface TopologyEdgeData {
  source: string;
  target: string;
}

export interface TopologyModel {
  nodes: TopologyNodeData[];
  edges: TopologyEdgeData[];
  activeCount: number;
  failedCount: number;
  totalTokens: number;
  totalCostUsd: number;
  totalDurationSeconds: number;
}

export const MAX_LABEL_LENGTH = 60;

/** Fission root is keyed by fission id so it can coexist with subagent task ids in a merged graph. */
function fissionRootId(fissionId: string): string {
  return `fission-${fissionId}`;
}

/** Fission child nodes live under the fission namespace so node ids never collide with subagent task ids. */
function fissionNodeId(fissionId: string, nodeId: string): string {
  return `fission-${fissionId}::${nodeId}`;
}

// ── Helpers ──────────────────────────────────────────────────────────

/** Strip long free-text labels so graph node labels stay readable on a single line. */
export function truncateLabel(text: string, maxLength = MAX_LABEL_LENGTH): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, maxLength - 1)}…`;
}

export function toneForStatus(status: string): TopologyTone {
  switch (status) {
    case 'running':
    case 'verifying':
      return 'active';
    case 'pending':
    case 'pending_approval':
    case 'checkpoint':
      return 'pending';
    case 'completed':
      return 'success';
    case 'failed':
    case 'timed_out':
    case 'interrupted':
    case 'cancelled':
    case 'cancelled_by_budget':
      return 'danger';
    case 'yielded':
      return 'warning';
    default:
      return 'muted';
  }
}

function emptyTopologyModel(): TopologyModel {
  return {
    nodes: [],
    edges: [],
    activeCount: 0,
    failedCount: 0,
    totalTokens: 0,
    totalCostUsd: 0,
    totalDurationSeconds: 0,
  };
}

// ── Builders ─────────────────────────────────────────────────────────

/** Build a graph from the live subagent tree. Dangling parents are dropped. */
export function buildTopologyModel(nodes: SubagentNode[]): TopologyModel {
  const model = emptyTopologyModel();
  if (nodes.length === 0) return model;

  const visible = nodes.filter((n) => !n.internal);
  const map: Record<string, TopologyNodeData> = {};
  for (const n of visible) {
    const verificationFailed = n.verification !== undefined && !n.verification.passed;
    const baseTone = toneForStatus(n.status);
    const tone: TopologyTone =
      baseTone === 'success' && verificationFailed ? 'danger' : baseTone;
    const data: TopologyNodeData = {
      taskId: n.task_id,
      label: truncateLabel(n.description || n.agent_type || n.task_id),
      agentType: n.agent_type,
      status: n.status,
      tone,
      progress: Number.isFinite(n.progress) ? n.progress : null,
      costUsd: extractCostUsd(n),
      tokens: extractTotalTokens(n),
      durationSeconds: n.duration_seconds ?? 0,
      error: n.error,
      parentTaskId: n.parent_task_id || undefined,
      verification: n.verification ? { passed: n.verification.passed } : undefined,
    };
    map[n.task_id] = data;
    model.nodes.push(data);

    if (tone === 'active') model.activeCount++;
    if (tone === 'danger') model.failedCount++;
    model.totalTokens += data.tokens;
    model.totalCostUsd += data.costUsd;
    model.totalDurationSeconds += data.durationSeconds;
  }

  for (const n of visible) {
    const parentId = n.parent_task_id;
    if (parentId && map[parentId]) {
      model.edges.push({ source: parentId, target: n.task_id });
    }
  }

  return model;
}

/**
 * Fallback model for the persisted fission topology when no live subagent
 * tree exists (e.g. after reload where the runtime has no in-memory state).
 */
export function buildFissionTopologyModel(topology: FissionTopology | null): TopologyModel {
  const model = emptyTopologyModel();
  if (!topology || topology.nodes.length === 0) return model;

  const rootId = fissionRootId(topology.fission_id);
  const hasActive = topology.nodes.some((n) => toneForStatus(n.status) === 'active');

  model.nodes.push({
    taskId: rootId,
    label: truncateLabel(topology.fission_id.slice(0, 8), 16),
    agentType: 'orchestrator',
    status: hasActive ? 'running' : 'completed',
    tone: hasActive ? 'active' : 'success',
    progress: null,
    costUsd: 0,
    tokens: 0,
    durationSeconds: 0,
    isRoot: true,
  });

  for (const n of topology.nodes) {
    const tone = toneForStatus(n.status);
    const childId = fissionNodeId(topology.fission_id, n.node_id);
    const data: TopologyNodeData = {
      taskId: childId,
      label: truncateLabel(n.objective || n.agent_type || n.node_id),
      agentType: n.agent_type,
      status: n.status,
      tone,
      progress: null,
      costUsd: n.cost_usd ?? 0,
      tokens: 0,
      durationSeconds: 0,
      error: n.error ?? undefined,
      parentTaskId: rootId,
    };
    model.nodes.push(data);
    model.edges.push({ source: rootId, target: childId });

    if (tone === 'active') model.activeCount++;
    if (tone === 'danger') model.failedCount++;
    model.totalCostUsd += data.costUsd;
  }

  return model;
}

/**
 * Combined model for the live subagent tree plus an active/persisted fission
 * swarm group. Both sources are independent (fission nodes are not part of the
 * subagent tree), so the canvas renders them side by side with accumulated
 * summary metrics.
 */
export function buildMergedTopologyModel(nodes: SubagentNode[], topology: FissionTopology | null): TopologyModel {
  const tree = buildTopologyModel(nodes);
  const fission = buildFissionTopologyModel(topology);
  if (fission.nodes.length === 0) return tree;

  return {
    nodes: [...tree.nodes, ...fission.nodes],
    edges: [...tree.edges, ...fission.edges],
    activeCount: tree.activeCount + fission.activeCount,
    failedCount: tree.failedCount + fission.failedCount,
    totalTokens: tree.totalTokens + fission.totalTokens,
    totalCostUsd: tree.totalCostUsd + fission.totalCostUsd,
    totalDurationSeconds: tree.totalDurationSeconds + fission.totalDurationSeconds,
  };
}
