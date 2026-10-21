/**
 * 分布式机队实时协同拓扑与观察者导演驾驶舱契约定义
 */

export type FleetHostType = 'mac_local' | 'cloud_sandbox' | 'gpu_cluster';
export type FleetNodeStatus = 'idle' | 'busy' | 'paused' | 'error';
export type DeliberationStatus = 'converging' | 'converged' | 'diverging';
export type DirectorExecutionMode = 'running' | 'paused' | 'stepping';

export interface FleetNode {
  id: string;
  label: string;
  role: string;
  hostType: FleetHostType;
  status: FleetNodeStatus;
  currentTask?: string;
  tokenBurnRate: number; // tokens/sec
  completedTasksCount: number;
}

export interface FleetLink {
  id: string;
  sourceId: string;
  targetId: string;
  workOrderTitle: string;
  progress: number; // 0 - 100
  status: 'transferring' | 'completed' | 'blocked';
}

export interface DeliberationMetrics {
  convergenceScore: number; // 0 - 100
  activeRounds: number;
  redundancyRatio: number; // 0.0 - 1.0 (反闲聊度量)
  totalTokenBurn: number;
  status: DeliberationStatus;
}

export interface DirectorIntervention {
  id: string;
  timestamp: number;
  targetNodeId: string;
  commandText: string;
  status: 'injected' | 'applied';
}

export interface FleetObserverState {
  executionMode: DirectorExecutionMode;
  selectedNodeId: string | null;
  nodes: FleetNode[];
  links: FleetLink[];
  metrics: DeliberationMetrics;
  interventions: DirectorIntervention[];
}
