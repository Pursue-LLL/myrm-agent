import { create } from 'zustand';
import type {
  DeliberationMetrics,
  DirectorExecutionMode,
  DirectorIntervention,
  FleetLink,
  FleetNode,
  FleetObserverState,
} from './fleetObserverTypes';

const INITIAL_NODES: FleetNode[] = [
  {
    id: 'node-mac-master',
    label: 'Mac Studio (主编排节点)',
    role: 'Orchestrator & Lead Planner',
    hostType: 'mac_local',
    status: 'busy',
    currentTask: '综合调度各节点产物与规约校验',
    tokenBurnRate: 48,
    completedTasksCount: 12,
  },
  {
    id: 'node-cloud-sandbox',
    label: 'Cloud Runner (Docker 沙箱)',
    role: 'Execution & Test Runner',
    hostType: 'cloud_sandbox',
    status: 'busy',
    currentTask: '运行 Vitest 单元测试与 oxlint 门禁',
    tokenBurnRate: 15,
    completedTasksCount: 8,
  },
  {
    id: 'node-gpu-cluster',
    label: 'GPU Cluster (深度推理算力)',
    role: 'Deep Reasoning & Code Refactor',
    hostType: 'gpu_cluster',
    status: 'idle',
    currentTask: '等待重构或架构审核工单就绪',
    tokenBurnRate: 0,
    completedTasksCount: 5,
  },
];

const INITIAL_LINKS: FleetLink[] = [
  {
    id: 'link-orch-sandbox',
    sourceId: 'node-mac-master',
    targetId: 'node-cloud-sandbox',
    workOrderTitle: '工单 #102: 执行单元测试门禁',
    progress: 75,
    status: 'transferring',
  },
  {
    id: 'link-orch-gpu',
    sourceId: 'node-mac-master',
    targetId: 'node-gpu-cluster',
    workOrderTitle: '工单 #103: 架构收敛性复核',
    progress: 100,
    status: 'completed',
  },
];

const INITIAL_METRICS: DeliberationMetrics = {
  convergenceScore: 88,
  activeRounds: 4,
  redundancyRatio: 0.08,
  totalTokenBurn: 14250,
  status: 'converging',
};

interface FleetObserverActions {
  setExecutionMode: (mode: DirectorExecutionMode) => void;
  pauseFleet: () => void;
  resumeFleet: () => void;
  stepFleet: () => void;
  selectNode: (nodeId: string | null) => void;
  injectDirectorCommand: (targetNodeId: string, commandText: string) => DirectorIntervention;
  updateNodeStatus: (nodeId: string, status: FleetNode['status']) => void;
  resetState: () => void;
}

export type FleetObserverStore = FleetObserverState & FleetObserverActions;

export const useFleetObserverStore = create<FleetObserverStore>((set, get) => ({
  executionMode: 'running',
  selectedNodeId: 'node-mac-master',
  nodes: INITIAL_NODES,
  links: INITIAL_LINKS,
  metrics: INITIAL_METRICS,
  interventions: [],

  setExecutionMode: (executionMode) => {
    set({ executionMode });
  },

  pauseFleet: () => {
    const state = get();
    const updatedNodes = state.nodes.map((n) => {
      if (n.status === 'busy') {
        return { ...n, status: 'paused' as const };
      }
      return n;
    });
    set({
      executionMode: 'paused',
      nodes: updatedNodes,
    });
  },

  resumeFleet: () => {
    const state = get();
    const updatedNodes = state.nodes.map((n) => {
      if (n.status === 'paused') {
        return { ...n, status: 'busy' as const };
      }
      return n;
    });
    set({
      executionMode: 'running',
      nodes: updatedNodes,
    });
  },

  stepFleet: () => {
    const state = get();
    // 单步步进：模拟当前链路进度向前推进 15%，收敛度微幅上升
    const updatedLinks = state.links.map((link) => {
      if (link.status === 'transferring') {
        const nextProg = Math.min(100, link.progress + 15);
        return {
          ...link,
          progress: nextProg,
          status: nextProg >= 100 ? ('completed' as const) : link.status,
        };
      }
      return link;
    });

    const nextConvergence = Math.min(100, state.metrics.convergenceScore + 2);
    set({
      executionMode: 'stepping',
      links: updatedLinks,
      metrics: {
        ...state.metrics,
        convergenceScore: nextConvergence,
        activeRounds: state.metrics.activeRounds + 1,
        status: nextConvergence >= 95 ? 'converged' : 'converging',
      },
    });
  },

  selectNode: (selectedNodeId) => {
    set({ selectedNodeId });
  },

  injectDirectorCommand: (targetNodeId, commandText) => {
    const state = get();
    const cleanCmd = commandText.trim();
    const intervention: DirectorIntervention = {
      id: `int-${Date.now()}`,
      timestamp: Date.now(),
      targetNodeId,
      commandText: cleanCmd,
      status: 'injected',
    };

    const updatedNodes = state.nodes.map((node) => {
      if (node.id === targetNodeId) {
        return {
          ...node,
          currentTask: `[导演指令] ${cleanCmd}`,
          status: 'busy' as const,
        };
      }
      return node;
    });

    set({
      interventions: [intervention, ...state.interventions],
      nodes: updatedNodes,
    });

    return intervention;
  },

  updateNodeStatus: (nodeId, status) => {
    const state = get();
    const updated = state.nodes.map((node) => {
      if (node.id === nodeId) {
        return { ...node, status };
      }
      return node;
    });
    set({ nodes: updated });
  },

  resetState: () => {
    set({
      executionMode: 'running',
      selectedNodeId: 'node-mac-master',
      nodes: INITIAL_NODES,
      links: INITIAL_LINKS,
      metrics: INITIAL_METRICS,
      interventions: [],
    });
  },
}));
