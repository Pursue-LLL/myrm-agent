/**
 * swarmCanvasTypes.ts
 * 多智能体弹性网格画布、动态并发聚焦透镜与无上限层级拓扑折叠套件类型定义
 */

export type SwarmWorkerStatus =
  | 'idle'
  | 'running'
  | 'waiting_approval'
  | 'completed'
  | 'failed';

export interface SwarmWorkerToolCall {
  id: string;
  toolName: string;
  summary: string;
  durationMs?: number;
  isError?: boolean;
}

export interface SwarmWorkerItem {
  id: string;
  name: string;
  role: string;
  avatarUrl?: string;
  colorTheme: string;
  status: SwarmWorkerStatus;
  currentTaskTitle: string;
  progressPercent: number;
  thinkingLogs: string[];
  toolCalls: SwarmWorkerToolCall[];
  createdAt: number;
}

export interface SwarmSummaryStats {
  total: number;
  completed: number;
  running: number;
  waitingApproval: number;
  failed: number;
  progressPercent: number;
}

export interface WorkerSteerPayload {
  workerId: string;
  instruction: string;
  timestamp: number;
}
