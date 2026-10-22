export type KanbanJobStatus =
  | 'triage'
  | 'todo'
  | 'ready'
  | 'running'
  | 'done'
  | 'blocked';

export type SwarmTopologyStage =
  | 'planning_root'
  | 'parallel_specialist'
  | 'verifier_gate'
  | 'synthesizer';

export type JobPriority = 'low' | 'normal' | 'high' | 'urgent';

export interface KanbanCommentItem {
  author: string;
  content: string;
  timestamp: number;
  isBlackboard: boolean;
}

export interface BlackboardEntryItem {
  entryId: string;
  jobId: string;
  stage: SwarmTopologyStage;
  author: string;
  payload: Record<string, string>;
  createdAt: number;
}

export interface KanbanJobItem {
  jobId: string;
  title: string;
  goal: string;
  approach: string;
  acceptanceCriteria: string[];
  status: KanbanJobStatus;
  priority: JobPriority;
  stage: SwarmTopologyStage;
  assignee?: string;
  dependencies: string[];
  blockedReason?: string;
  worktreePath?: string;
  skills: string[];
  comments: KanbanCommentItem[];
  resultSummary?: string;
  resultMetadata: Record<string, string>;
  failureCount: number;
  goalMode: boolean;
  goalMaxTurns: number;
  lastHeartbeatTimestamp: number;
  createdAt: number;
  updatedAt: number;
}

export interface BatchRunnerStatus {
  totalJobs: number;
  doneJobs: number;
  readyJobs: number;
  runningJobs: number;
  blockedJobs: number;
  resumeAvailable: boolean;
  trajectoriesCollected: number;
}

export const DEFAULT_KANBAN_JOBS: KanbanJobItem[] = [
  {
    jobId: 'job-root-01',
    title: 'Architecture Blueprint Formulation',
    goal: 'Define multi-agent queue & 12-way dogfooding runner',
    approach: 'Hermes Kanban SQLite spec & Swarm 4-stage topology',
    acceptanceCriteria: [
      '5-state lifecycle verified',
      '4h heartbeat deadlock reclamation supported',
    ],
    status: 'done',
    priority: 'high',
    stage: 'planning_root',
    assignee: 'lead_architect',
    dependencies: [],
    worktreePath: '.worktrees/job-root-01',
    skills: ['architecture', 'swarm'],
    comments: [
      {
        author: 'lead_architect',
        content: '[swarm:blackboard] {"status": "planned", "stages": "4"}',
        timestamp: Date.now() - 3600000,
        isBlackboard: true,
      },
    ],
    resultSummary: 'Planning complete. DAG fan-out decomposed to specialists.',
    resultMetadata: { stages: '4', spec: 'v1.0' },
    failureCount: 0,
    goalMode: true,
    goalMaxTurns: 15,
    lastHeartbeatTimestamp: Date.now() - 1800000,
    createdAt: Date.now() - 7200000,
    updatedAt: Date.now() - 1800000,
  },
  {
    jobId: 'job-sub-02',
    title: '12-Way Batch Runner Implementation',
    goal: 'Execute massive parallel workers with --resume checkpoint',
    approach: 'Process pool coordination with HuggingFace JSONL trajectory export',
    acceptanceCriteria: ['12 parallel instances', 'Zero loss on crash'],
    status: 'running',
    priority: 'high',
    stage: 'parallel_specialist',
    assignee: 'worker-slot-rr-0',
    dependencies: ['job-root-01'],
    worktreePath: '.worktrees/job-sub-02',
    skills: ['concurrency', 'checkpointing'],
    comments: [],
    resultMetadata: {},
    failureCount: 0,
    goalMode: false,
    goalMaxTurns: 15,
    lastHeartbeatTimestamp: Date.now() - 60000,
    createdAt: Date.now() - 3600000,
    updatedAt: Date.now() - 60000,
  },
  {
    jobId: 'job-sub-03',
    title: 'Verifier Gate Quality Audit',
    goal: 'Run unit & linter tests across all worktrees',
    approach: 'Isolated worktree validation',
    acceptanceCriteria: ['100% test pass', '0 lint warnings'],
    status: 'ready',
    priority: 'normal',
    stage: 'verifier_gate',
    dependencies: ['job-sub-02'],
    worktreePath: '.worktrees/job-sub-03',
    skills: ['qa', 'audit'],
    comments: [],
    resultMetadata: {},
    failureCount: 0,
    goalMode: true,
    goalMaxTurns: 15,
    lastHeartbeatTimestamp: Date.now() - 3600000,
    createdAt: Date.now() - 3600000,
    updatedAt: Date.now() - 3600000,
  },
];
