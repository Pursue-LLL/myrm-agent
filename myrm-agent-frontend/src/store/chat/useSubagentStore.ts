import { create } from 'zustand';

import { mergeTeammateEntries, normalizeTeammateEntry } from '@/lib/utils/teammateMessage';

export type SubagentStatus =
  | 'pending'
  | 'running'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'timed_out'
  | 'cancelled'
  | 'cancelled_by_budget'
  | 'pending_approval'
  | 'yielded'
  | 'interrupted'
  | 'checkpoint';
export type SubagentMetadataValue =
  | string
  | number
  | boolean
  | null
  | SubagentMetadataValue[]
  | { [key: string]: SubagentMetadataValue };

export interface TeammateMessageEntry {
  message_id?: string;
  from_task_id: string;
  to_task_id: string;
  body: string;
  created_at: number;
}

export type StreamEntryKind = 'tool' | 'progress' | 'thinking' | 'error';

export interface StreamEntry {
  kind: StreamEntryKind;
  text: string;
  isError?: boolean;
  timestamp: number;
  durationMs?: number;
}

const MAX_STREAM = 30;

export interface SubagentNode {
  task_id: string;
  parent_task_id: string;
  agent_type: string;
  description: string;
  status: SubagentStatus;
  progress: number;
  last_tool?: string;
  duration_seconds?: number;
  error?: string;
  role?: string;
  control_scope?: string;
  policy_reason?: string;
  policy_details?: string;
  budget?: Record<string, SubagentMetadataValue>;
  startedAt?: number;
  estimatedTotalDuration?: number;
  overtimeDismissed?: boolean;
  teammateMessages?: TeammateMessageEntry[];
  /** Hydrated from API `teammate_messages` */
  teammate_messages?: TeammateMessageEntry[];
  stream?: StreamEntry[];
}

export interface FissionTopologyNode {
  node_id: string;
  agent_type: string;
  objective: string;
  status: string;
  error?: string | null;
  cost_usd?: number;
}

export interface FissionTopology {
  fission_id: string;
  nodes: FissionTopologyNode[];
  total_cost_usd: number;
}

export interface SubagentStore {
  nodes: Record<string, SubagentNode>;
  fissionBatch: {
    active: boolean;
    total: number;
    completed: number;
    failed: number;
    partial: boolean;
  } | null;
  fissionTopology: FissionTopology | null;

  // Actions
  upsertNode: (nodeUpdate: Partial<SubagentNode> & { task_id: string }) => void;
  updateProgress: (taskId: string, progress: number, lastTool?: string) => void;
  updateEstimate: (taskId: string, etaSeconds: number) => void;
  dismissOvertime: (taskId: string) => void;
  completeNode: (taskId: string, status: SubagentStatus, error?: string) => void;
  setNodes: (nodes: SubagentNode[]) => void;
  appendTeammateMessage: (entry: TeammateMessageEntry) => void;
  appendStream: (taskId: string, entry: StreamEntry) => void;
  setFissionBatch: (
    batch: {
      active: boolean;
      total: number;
      completed: number;
      failed: number;
      partial: boolean;
    } | null,
  ) => void;
  setFissionTopology: (topology: FissionTopology | null) => void;
  clear: () => void;
}

export const useSubagentStore = create<SubagentStore>((set) => ({
  nodes: {},
  fissionBatch: null,
  fissionTopology: null,

  upsertNode: (nodeUpdate) =>
    set((state) => {
      const existing = state.nodes[nodeUpdate.task_id] || {
        task_id: nodeUpdate.task_id,
        parent_task_id: '',
        agent_type: 'unknown',
        description: '',
        status: 'running',
        progress: 0,
      };

      return {
        nodes: {
          ...state.nodes,
          [nodeUpdate.task_id]: { ...existing, ...nodeUpdate },
        },
      };
    }),

  updateProgress: (taskId, progress, lastTool) =>
    set((state) => {
      if (!state.nodes[taskId]) return state;
      return {
        nodes: {
          ...state.nodes,
          [taskId]: {
            ...state.nodes[taskId],
            progress,
            last_tool: lastTool || state.nodes[taskId].last_tool,
          },
        },
      };
    }),

  updateEstimate: (taskId, etaSeconds) =>
    set((state) => {
      const node = state.nodes[taskId];
      if (!node || !node.startedAt) return state;
      const elapsedMs = Date.now() - node.startedAt;
      const estimatedTotalDuration = elapsedMs + etaSeconds * 1000;
      return {
        nodes: {
          ...state.nodes,
          [taskId]: { ...node, estimatedTotalDuration },
        },
      };
    }),

  dismissOvertime: (taskId) =>
    set((state) => {
      if (!state.nodes[taskId]) return state;
      return {
        nodes: {
          ...state.nodes,
          [taskId]: { ...state.nodes[taskId], overtimeDismissed: true },
        },
      };
    }),

  completeNode: (taskId, status, error) =>
    set((state) => {
      if (!state.nodes[taskId]) return state;
      return {
        nodes: {
          ...state.nodes,
          [taskId]: {
            ...state.nodes[taskId],
            status,
            error,
            progress: status === 'completed' ? 100 : state.nodes[taskId].progress,
          },
        },
      };
    }),

  setNodes: (nodes) =>
    set((state) => {
      const map = { ...state.nodes };
      nodes.forEach((n) => {
        const existing = map[n.task_id];
        const apiTeammate = (n.teammate_messages ?? []).map((row) => normalizeTeammateEntry(row));
        map[n.task_id] = {
          ...existing,
          ...n,
          teammateMessages: mergeTeammateEntries(existing?.teammateMessages, apiTeammate),
        };
      });
      return { nodes: map };
    }),

  appendTeammateMessage: (entry) =>
    set((state) => {
      const nodes = { ...state.nodes };
      const targets = [entry.to_task_id, entry.from_task_id];
      let changed = false;
      for (const taskId of targets) {
        const node = nodes[taskId];
        if (!node) continue;
        const prev = node.teammateMessages ?? [];
        if (entry.message_id && prev.some((m) => m.message_id === entry.message_id)) {
          continue;
        }
        nodes[taskId] = {
          ...node,
          teammateMessages: [...prev, entry].slice(-20),
        };
        changed = true;
      }
      if (!changed) return state;
      return { nodes };
    }),

  appendStream: (taskId, entry) =>
    set((state) => {
      const node = state.nodes[taskId];
      if (!node) return state;
      const prev = node.stream ?? [];
      const last = prev[prev.length - 1];
      if (last?.kind === entry.kind && last.text === entry.text) return state;
      const next = prev.length >= MAX_STREAM ? [...prev.slice(1), entry] : [...prev, entry];
      return {
        nodes: { ...state.nodes, [taskId]: { ...node, stream: next } },
      };
    }),

  setFissionBatch: (batch) => set({ fissionBatch: batch }),

  setFissionTopology: (topology) => set({ fissionTopology: topology }),

  clear: () => set({ nodes: {}, fissionBatch: null, fissionTopology: null }),
}));

if (typeof window !== 'undefined') {
  (window as Window & { __myrmSubagentStore?: typeof useSubagentStore }).__myrmSubagentStore = useSubagentStore;
}

const OVERTIME_ABSOLUTE_THRESHOLD_MS = 60_000;
const OVERTIME_RATIO = 2;
const OVERTIME_NO_ETA_THRESHOLD_MS = 90_000;
const OVERTIME_NO_ETA_PROGRESS_THRESHOLD = 30;

export function isNodeOvertime(node: SubagentNode): boolean {
  if (node.status !== 'running' || !node.startedAt || node.overtimeDismissed) return false;
  const elapsed = Date.now() - node.startedAt;
  if (elapsed < OVERTIME_ABSOLUTE_THRESHOLD_MS) return false;
  if (node.estimatedTotalDuration) {
    return elapsed > node.estimatedTotalDuration * OVERTIME_RATIO;
  }
  return elapsed > OVERTIME_NO_ETA_THRESHOLD_MS && node.progress < OVERTIME_NO_ETA_PROGRESS_THRESHOLD;
}

// Helper selector to get tree structure
export const selectSubagentTree = (state: SubagentStore) => {
  const nodes = Object.values(state.nodes);
  const rootNodes: (SubagentNode & { children: SubagentNode[] })[] = [];
  const map: Record<string, SubagentNode & { children: SubagentNode[] }> = {};

  nodes.forEach((n) => {
    map[n.task_id] = { ...n, children: [] };
  });

  nodes.forEach((n) => {
    if (n.parent_task_id && map[n.parent_task_id]) {
      map[n.parent_task_id].children.push(map[n.task_id]);
    } else {
      rootNodes.push(map[n.task_id]);
    }
  });

  return rootNodes;
};
