export type ActorType =
  | 'human_user'
  | 'local_agent'
  | 'cloud_agent'
  | 'system_orchestrator';

export type OperationType =
  | 'file_modify'
  | 'file_create'
  | 'file_delete'
  | 'tool_execution'
  | 'git_commit';

export type RollbackStatus =
  | 'success'
  | 'conflict_detected'
  | 'already_rolled_back'
  | 'node_not_found';

export interface TimelineNodeItem {
  nodeId: string;
  sessionId: string;
  actorId: string;
  actorName: string;
  actorType: ActorType;
  operationType: OperationType;
  filePath: string;
  lineStart?: number;
  lineEnd?: number;
  beforeContent?: string;
  afterContent?: string;
  diffSummary?: string;
  isRolledBack: boolean;
  timestamp: number;
  metadata?: Record<string, string>;
}

export interface RollbackResultItem {
  nodeId: string;
  status: RollbackStatus;
  filePath: string;
  restoredContent?: string;
  conflictReason?: string;
  rollbackTimestamp: number;
}

export interface VisualTimelineCherryPickCardProps {
  sessionId?: string;
  chatId?: string;
  onDismiss?: () => void;
  onRollbackComplete?: (result: RollbackResultItem) => void;
}

export const INITIAL_TIMELINE_NODES: TimelineNodeItem[] = [
  {
    nodeId: 'node-init-01',
    sessionId: 'sess-default',
    actorId: 'human-user-01',
    actorName: 'Lead Architect',
    actorType: 'human_user',
    operationType: 'file_create',
    filePath: 'src/config/gateway.ts',
    lineStart: 1,
    lineEnd: 25,
    beforeContent: '',
    afterContent: 'export const GATEWAY_TIMEOUT = 30000;\nexport const MAX_RETRY = 3;',
    diffSummary: 'Initial gateway configuration bootstrap',
    isRolledBack: false,
    timestamp: Date.now() - 3600000,
  },
  {
    nodeId: 'node-sub-02',
    sessionId: 'sess-default',
    actorId: 'agent-db-worker',
    actorName: 'Database Optimizer Bot',
    actorType: 'local_agent',
    operationType: 'file_modify',
    filePath: 'src/config/gateway.ts',
    lineStart: 2,
    lineEnd: 2,
    beforeContent: 'export const MAX_RETRY = 3;',
    afterContent: 'export const MAX_RETRY = 5;\nexport const DB_POOL_SIZE = 20;',
    diffSummary: 'Enlarge pool size and retries for PostgreSQL',
    isRolledBack: false,
    timestamp: Date.now() - 1800000,
  },
  {
    nodeId: 'node-bug-03',
    sessionId: 'sess-default',
    actorId: 'agent-junior-dev',
    actorName: 'Junior Scaffold Bot',
    actorType: 'local_agent',
    operationType: 'file_modify',
    filePath: 'src/auth/token_guard.py',
    lineStart: 45,
    lineEnd: 46,
    beforeContent: 'VERIFY_SIGNATURE = True',
    afterContent: 'VERIFY_SIGNATURE = False  # Temporary skip',
    diffSummary: 'Dangerous bypass of signature validation',
    isRolledBack: false,
    timestamp: Date.now() - 600000,
  },
];
