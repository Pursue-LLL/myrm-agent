/**
 * Type contracts for Multi-Step Workflow Execution Traceability & Breakpoint Replay Cockpit.
 * Adheres strictly to zero-emoji and explicit type constraints (no `any`).
 */

export type WorkflowStage =
  | 'intake'
  | 'planning'
  | 'dispatch'
  | 'execution_validation'
  | 'closure';

export type WorkflowNodeStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'retrying'
  | 'replaying';

export type PayloadValue = string | number | boolean | string[];

export interface FourDimValidationScore {
  completeness: number;
  accuracy: number;
  compliance: number;
  relevance: number;
  composite_score: number;
}

export interface WorkflowNodeSnapshot {
  node_id: string;
  step_number: number;
  title: string;
  stage: WorkflowStage;
  status: WorkflowNodeStatus;
  input_payload: Record<string, PayloadValue>;
  output_payload: Record<string, PayloadValue> | null;
  prompt_excerpt: string | null;
  tools_called: string[];
  tokens_consumed: number;
  validation_scores: FourDimValidationScore | null;
  duration_ms: number;
  created_at: string;
  identity_hash: string;
}

export interface WorkflowTraceResponse {
  workflow_id: string;
  task_id: string;
  title: string;
  current_stage: WorkflowStage;
  nodes: WorkflowNodeSnapshot[];
  total_tokens: number;
  total_duration_ms: number;
}

export interface ReplayFromNodeRequest {
  workflow_id: string;
  node_id: string;
  override_inputs?: Record<string, PayloadValue>;
  steer_prompt?: string | null;
}

export interface ReplayFromNodeResponse {
  workflow_id: string;
  replayed_from_node_id: string;
  status: 'resumed' | 'completed' | 'failed';
  message: string;
  replayed_nodes: WorkflowNodeSnapshot[];
}
