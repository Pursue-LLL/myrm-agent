export type PeerStatus = 'online' | 'stale' | 'offline';

export type EnvelopeType = 'prompt' | 'response' | 'ping' | 'pong';

export interface PeerInfo {
  sessionId: string;
  name: string;
  purpose: string;
  model: string;
  pid: number;
  endpoint: string;
  cwd: string;
  startedAt: number;
  heartbeatAt: number;
  contextUsedPct: number;
  queueDepth: number;
  status: PeerStatus;
}

export interface EnvelopeItem {
  msgId: string;
  type: EnvelopeType;
  senderName: string;
  targetName: string;
  hops: number;
  prompt?: string;
  response?: string;
  error?: string;
  timestamp: number;
}

export interface MeshAuditLog {
  timestamp: number;
  eventType: string;
  node: string;
  project: string;
  detail: string;
}

export const DEFAULT_PEERS: PeerInfo[] = [
  {
    sessionId: 'sess-planner-01',
    name: 'planner',
    purpose: 'System Architecture & Task Orchestrator',
    model: 'gpt-5-turbo',
    pid: 14820,
    endpoint: '/tmp/.myrm/coms/sockets/planner.sock',
    cwd: '/workspace/project',
    startedAt: Date.now() - 3600000,
    heartbeatAt: Date.now() - 2000,
    contextUsedPct: 32.5,
    queueDepth: 1,
    status: 'online',
  },
  {
    sessionId: 'sess-coder-02',
    name: 'coder',
    purpose: 'Core Python & TypeScript Implementer',
    model: 'claude-3-7-sonnet',
    pid: 14821,
    endpoint: '/tmp/.myrm/coms/sockets/coder.sock',
    cwd: '/workspace/project',
    startedAt: Date.now() - 3600000,
    heartbeatAt: Date.now() - 4000,
    contextUsedPct: 68.0,
    queueDepth: 2,
    status: 'online',
  },
  {
    sessionId: 'sess-auditor-03',
    name: 'security-auditor',
    purpose: 'Zero-Trust Policy & Static AST Linter',
    model: 'deepseek-r1',
    pid: 14822,
    endpoint: '/tmp/.myrm/coms/sockets/auditor.sock',
    cwd: '/workspace/project',
    startedAt: Date.now() - 1800000,
    heartbeatAt: Date.now() - 15000,
    contextUsedPct: 18.2,
    queueDepth: 0,
    status: 'online',
  },
];

export const DEFAULT_AUDIT_LOGS: MeshAuditLog[] = [
  {
    timestamp: Date.now() - 3600000,
    eventType: 'NODE_STARTED',
    node: 'planner',
    project: 'default',
    detail: 'Registered at /tmp/.myrm/coms/sockets/planner.sock',
  },
  {
    timestamp: Date.now() - 3600000,
    eventType: 'NODE_STARTED',
    node: 'coder',
    project: 'default',
    detail: 'Registered at /tmp/.myrm/coms/sockets/coder.sock',
  },
  {
    timestamp: Date.now() - 1200000,
    eventType: 'SEND_PROMPT',
    node: 'planner',
    project: 'default',
    detail: 'Dispatched prompt envelope to coder (hops: 0)',
  },
  {
    timestamp: Date.now() - 1198000,
    eventType: 'REPLY_RECEIVED',
    node: 'coder',
    project: 'default',
    detail: 'Delivered response to planner in 2.1ms (hops: 1)',
  },
];
