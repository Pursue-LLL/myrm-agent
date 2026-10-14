/**
 * [INPUT]
 * None
 * [OUTPUT]
 * Strongly typed TypeScript interfaces for Multi-Client Bidirectional Approval Protocol and Visual Diff.
 * [POS]
 * src/components/approval/visual-diff/visualDiffTypes.ts
 */

export type ApprovalActionKind = 'file_write' | 'command_exec' | 'tool_call' | 'outbound_request';

export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical';

export type DecisionKind = 'allow' | 'reject' | 'remember_session';

export type ClientType = 'web' | 'desktop' | 'mobile';

export interface FileDiffPayload {
  file_path: string;
  old_content?: string | null;
  new_content: string;
  unified_diff: string;
  added_lines: number;
  removed_lines: number;
  is_new_file: boolean;
  is_deletion: boolean;
}

export interface CommandRiskPayload {
  command: string;
  cwd: string;
  risk_severity: RiskSeverity;
  risk_reasons: string[];
  blast_radius_paths: string[];
}

export interface StructuredApprovalRequest {
  approval_id: string;
  session_id: string;
  sequence_id: number;
  kind: ApprovalActionKind;
  summary: string;
  file_diff?: FileDiffPayload | null;
  command_risk?: CommandRiskPayload | null;
  created_at: number;
  expires_at?: number | null;
  allowed_decisions: DecisionKind[];
}

export interface StructuredApprovalDecision {
  approval_id: string;
  decision: DecisionKind;
  decided_by?: string;
  client_type?: ClientType;
  reason?: string | null;
  decided_at?: number;
}

export interface ApprovalAck {
  approval_id: string;
  sequence_id: number;
  acknowledged: boolean;
  status: string;
}
