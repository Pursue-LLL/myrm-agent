export type DagNodeStatus =
  | 'PENDING'
  | 'READY'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'SKIPPED'
  | 'REJECTED_LOOPBACK';

export type DagNodeType =
  | 'ARCHITECT'
  | 'CODER'
  | 'CRITIC_REVIEWER'
  | 'TESTER'
  | 'SECURITY_AUDITOR';

export interface DagNodeItem {
  id: string;
  name: string;
  nodeType: DagNodeType;
  status: DagNodeStatus;
  dependencies: string[];
  assignedSubagent: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
  errorMessage?: string;
  retryCount: number;
  feedbackHistory: string[];
}

export interface DagEdgeItem {
  fromNode: string;
  toNode: string;
  condition?: string;
}

export interface DagExecutionSnapshotItem {
  snapshotId: string;
  workflowId: string;
  createdAt: string;
  statusCounts: Record<DagNodeStatus, number>;
  nodes: Record<string, DagNodeItem>;
  edges: DagEdgeItem[];
}

export interface DagWorkflowStateItem {
  workflowId: string;
  chatId: string;
  isPaused: boolean;
  nodes: Record<string, DagNodeItem>;
  edges: DagEdgeItem[];
  readyQueue: string[];
  historySnapshots: DagExecutionSnapshotItem[];
}

export const DEFAULT_DAG_NODES: Record<string, DagNodeItem> = {
  plan: {
    id: 'plan',
    name: 'Architecture Planning',
    nodeType: 'ARCHITECT',
    status: 'COMPLETED',
    dependencies: [],
    assignedSubagent: 'lead_architect',
    inputs: { requirement: 'Topic 12 Orchestration' },
    outputs: { spec: 'architecture_v1.json' },
    retryCount: 0,
    feedbackHistory: [],
  },
  code: {
    id: 'code',
    name: 'Implementation Wave',
    nodeType: 'CODER',
    status: 'COMPLETED',
    dependencies: ['plan'],
    assignedSubagent: 'backend_coder',
    inputs: { spec: 'architecture_v1.json' },
    outputs: { artifact: 'harness_patch.py' },
    retryCount: 0,
    feedbackHistory: [],
  },
  review: {
    id: 'review',
    name: 'Critic Audit & Review',
    nodeType: 'CRITIC_REVIEWER',
    status: 'FAILED',
    dependencies: ['code'],
    assignedSubagent: 'code_critic',
    inputs: { artifact: 'harness_patch.py' },
    outputs: {},
    errorMessage: 'Lint violation: cyclic dependency in adapter bridge',
    retryCount: 1,
    feedbackHistory: ['Please decouple adapter bridge from circular refs'],
  },
  deploy: {
    id: 'deploy',
    name: 'Smoke Test & Delivery',
    nodeType: 'TESTER',
    status: 'PENDING',
    dependencies: ['review'],
    assignedSubagent: 'qa_engineer',
    inputs: {},
    outputs: {},
    retryCount: 0,
    feedbackHistory: [],
  },
};

export const DEFAULT_DAG_EDGES: DagEdgeItem[] = [
  { fromNode: 'plan', toNode: 'code' },
  { fromNode: 'code', toNode: 'review' },
  { fromNode: 'review', toNode: 'deploy' },
];
