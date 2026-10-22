/**
 * [INPUT]
 * - quadGraphTypes: GraphLayerType, NodeStatus, GraphNode, GraphEdge, QuadGraphModel, NodeSteerPayload
 *
 * [OUTPUT]
 * - useQuadGraphStore: Zustand store for quad-graph layer switching, node inspection, and real-time steering
 *
 * [POS]
 * State management for QuadGraphMultiLayerExecutionCanvasAndTopologyInspectionHUD (Item 50 P0).
 * Strictly under 220 lines. Zero `any`.
 */

import { create } from 'zustand';
import type {
  GraphLayerType,
  GraphNode,
  GraphEdge,
  NodeStatus,
  NodeSteerPayload,
  QuadGraphSummary,
} from './quadGraphTypes';

interface QuadGraphState {
  activeLayer: GraphLayerType;
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string | null;
  isInspectionOpen: boolean;
  hoveredNodeId: string | null;

  setActiveLayer: (layer: GraphLayerType) => void;
  setNodesAndEdges: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  selectNode: (nodeId: string | null) => void;
  setInspectionOpen: (isOpen: boolean) => void;
  setHoveredNodeId: (nodeId: string | null) => void;
  updateNodeStatus: (nodeId: string, status: NodeStatus, output?: string, error?: string) => void;
  steerNode: (payload: NodeSteerPayload) => void;
  resetToDemoModel: () => void;
  getSummary: () => QuadGraphSummary;
}

const DEFAULT_DEMO_NODES: GraphNode[] = [
  // Task Graph
  { id: 'task_1', label: '1. 需求意图解析与业务建模', layer: 'task', status: 'completed', durationMs: 420, dependencies: [] },
  { id: 'task_2', label: '2. 数据库表结构与索引设计', layer: 'task', status: 'completed', durationMs: 850, dependencies: ['task_1'] },
  { id: 'task_3', label: '3. 核心 API 路由与鉴权中介实现', layer: 'task', status: 'running', durationMs: 1200, dependencies: ['task_2'] },
  { id: 'task_4', label: '4. 前端交互仪表盘与状态绑定', layer: 'task', status: 'verifying', durationMs: 350, dependencies: ['task_3'] },
  { id: 'task_5', label: '5. 端到端安全沙箱回归测试', layer: 'task', status: 'pending', durationMs: 0, dependencies: ['task_4'] },

  // Workflow Graph
  { id: 'wf_1', label: 'Prompt 语义分解', layer: 'workflow', status: 'completed', durationMs: 210, role: 'LLM Parser' },
  { id: 'wf_2', label: '知识库向量混合召回', layer: 'workflow', status: 'completed', durationMs: 380, role: 'Qdrant Rerank' },
  { id: 'wf_3', label: '代码沙箱执行与补丁生成', layer: 'workflow', status: 'running', durationMs: 980, role: 'Sandbox Bash' },
  { id: 'wf_4', label: '静态类型检查与 Lint 门禁', layer: 'workflow', status: 'pending', durationMs: 0, role: 'oxlint Gate' },

  // Team Graph
  { id: 'team_planner', label: '架构规划官 (Planner)', layer: 'team', status: 'completed', role: 'Chief Architect' },
  { id: 'team_coder', label: '代码工程师 (Coder)', layer: 'team', status: 'running', role: 'FullStack Engineer' },
  { id: 'team_reviewer', label: '审查仲裁官 (Reviewer)', layer: 'team', status: 'verifying', role: 'Security Guard' },
  { id: 'team_tester', label: '测试质检员 (Tester)', layer: 'team', status: 'pending', role: 'QA Lead' },

  // Communication Graph
  { id: 'comm_hub', label: '中央调度中枢 (Dispatcher)', layer: 'communication', status: 'completed', role: 'Hub' },
  { id: 'comm_coder_msg', label: 'Coder 实时事件总线', layer: 'communication', status: 'running', role: 'Event Stream' },
  { id: 'comm_reviewer_msg', label: 'Reviewer 反馈拦截通道', layer: 'communication', status: 'verifying', role: 'Audit Log' },
];

const DEFAULT_DEMO_EDGES: GraphEdge[] = [
  // Task Edges
  { id: 'te_1', source: 'task_1', target: 'task_2', layer: 'task', label: 'DAG' },
  { id: 'te_2', source: 'task_2', target: 'task_3', layer: 'task', label: 'DAG' },
  { id: 'te_3', source: 'task_3', target: 'task_4', layer: 'task', label: 'DAG', active: true },
  { id: 'te_4', source: 'task_4', target: 'task_5', layer: 'task', label: 'DAG' },

  // Workflow Edges
  { id: 'we_1', source: 'wf_1', target: 'wf_2', layer: 'workflow', label: 'pipe' },
  { id: 'we_2', source: 'wf_2', target: 'wf_3', layer: 'workflow', label: 'pipe', active: true },
  { id: 'we_3', source: 'wf_3', target: 'wf_4', layer: 'workflow', label: 'pipe' },

  // Team Edges
  { id: 'tme_1', source: 'team_planner', target: 'team_coder', layer: 'team', label: 'assign' },
  { id: 'tme_2', source: 'team_coder', target: 'team_reviewer', layer: 'team', label: 'review', active: true },
  { id: 'tme_3', source: 'team_reviewer', target: 'team_tester', layer: 'team', label: 'verify' },

  // Communication Edges
  { id: 'ce_1', source: 'comm_hub', target: 'comm_coder_msg', layer: 'communication', label: 'stream', flowCount: 142, active: true },
  { id: 'ce_2', source: 'comm_coder_msg', target: 'comm_reviewer_msg', layer: 'communication', label: 'audit', flowCount: 38 },
];

export const useQuadGraphStore = create<QuadGraphState>((set, get) => ({
  activeLayer: 'task',
  nodes: DEFAULT_DEMO_NODES,
  edges: DEFAULT_DEMO_EDGES,
  selectedNodeId: null,
  isInspectionOpen: false,
  hoveredNodeId: null,

  setActiveLayer: (layer) => {
    set({ activeLayer: layer });
  },

  setNodesAndEdges: (nodes, edges) => {
    set({ nodes, edges });
  },

  selectNode: (nodeId) => {
    set({
      selectedNodeId: nodeId,
      isInspectionOpen: Boolean(nodeId),
    });
  },

  setInspectionOpen: (isOpen) => {
    set({
      isInspectionOpen: isOpen,
      selectedNodeId: isOpen ? get().selectedNodeId : null,
    });
  },

  setHoveredNodeId: (nodeId) => {
    set({ hoveredNodeId: nodeId });
  },

  updateNodeStatus: (nodeId, status, output, error) => {
    set((state) => ({
      nodes: state.nodes.map((n) => {
        if (n.id === nodeId) {
          return {
            ...n,
            status,
            outputSnapshot: output ?? n.outputSnapshot,
            error: error ?? n.error,
          };
        }
        return n;
      }),
    }));
  },

  steerNode: (payload) => {
    const { nodeId, action, instruction } = payload;
    set((state) => ({
      nodes: state.nodes.map((n) => {
        if (n.id === nodeId) {
          if (action === 'pause') {
            return { ...n, status: 'pending', outputSnapshot: `[PAUSED]: ${instruction}` };
          }
          if (action === 'resume' || action === 'steer') {
            return { ...n, status: 'running', inputSnapshot: instruction || n.inputSnapshot };
          }
          if (action === 'retry') {
            return { ...n, status: 'running', error: undefined };
          }
        }
        return n;
      }),
    }));
  },

  resetToDemoModel: () => {
    set({
      nodes: DEFAULT_DEMO_NODES,
      edges: DEFAULT_DEMO_EDGES,
      selectedNodeId: null,
      isInspectionOpen: false,
      hoveredNodeId: null,
    });
  },

  getSummary: () => {
    const { nodes, edges } = get();
    return {
      totalNodes: nodes.length,
      totalEdges: edges.length,
      completedNodes: nodes.filter((n) => n.status === 'completed').length,
      runningNodes: nodes.filter((n) => n.status === 'running' || n.status === 'verifying').length,
      failedNodes: nodes.filter((n) => n.status === 'failed').length,
      totalDurationMs: nodes.reduce((acc, n) => acc + (n.durationMs || 0), 0),
    };
  },
}));
