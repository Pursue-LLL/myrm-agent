export type SpeculativeAckStatus =
  | 'received'
  | 'intent_analyzed'
  | 'tool_binding'
  | 'streaming_started';

export interface SpeculativeAckPayload {
  id: string;
  messageId: string;
  status: SpeculativeAckStatus;
  intentSummary: string;
  speculativeTools: string[];
  ackTimestamp: number;
  elapsedMs: number;
}

export type DagStepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'bypassed';

export interface DagStepNode {
  id: string;
  name: string;
  description?: string;
  status: DagStepStatus;
  parallelGroupId?: string;
  elapsedMs?: number;
  isCriticalPath: boolean;
}

export interface DagTimelineState {
  dagId: string;
  messageId: string;
  totalSteps: number;
  completedSteps: number;
  isAllCompleted: boolean;
  steps: DagStepNode[];
  startedAt: number;
  completedAt?: number;
}

export interface EmitEarlyAckParams {
  id?: string;
  messageId: string;
  intentSummary?: string;
  tools?: string[];
  ackTimestamp?: number;
}

export interface InitDagTimelineParams {
  dagId: string;
  messageId: string;
  steps: Array<{
    id: string;
    name: string;
    description?: string;
    parallelGroupId?: string;
    isCriticalPath?: boolean;
  }>;
}
