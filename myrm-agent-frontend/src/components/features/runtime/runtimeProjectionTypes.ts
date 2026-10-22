/**
 * TypeScript Data Contracts for Pure Functional Run Projections.
 * Strict zero-any adherence and alignment with FastAPI backend models.
 */

export type SurfaceViewType = 'chat' | 'runtime_console' | 'deliverables' | 'audit';

export type AttemptStatus = 'pending' | 'executing' | 'completed' | 'failed' | 'retrying';

export interface AttemptRecord {
  attempt_id: string;
  run_id: string;
  attempt_number: number;
  status: AttemptStatus;
  started_at_ms: number;
  finished_at_ms?: number | null;
  duration_ms?: number | null;
  tokens_in: number;
  tokens_out: number;
  tokens_per_sec: number;
  error_reason?: string | null;
  stack_trace?: string | null;
  diff_summary?: string | null;
}

export interface RunProjectionEvent {
  event_id: string;
  run_id: string;
  event_type: string;
  timestamp_ms: number;
  payload: Record<string, unknown>;
}

export interface DeliverableItem {
  deliverable_id: string;
  title: string;
  type: string;
  path_or_uri: string;
  status: string;
  created_at_ms: number;
}

export interface AuditLedgerEntry {
  audit_id: string;
  action: string;
  actor: string;
  risk_level: string;
  decision: string;
  timestamp_ms: number;
}

export interface RunStateSnapshot {
  run_id: string;
  title: string;
  status: string;
  active_surface: SurfaceViewType;
  current_attempt: number;
  attempts: AttemptRecord[];
  deliverables: DeliverableItem[];
  audit_entries: AuditLedgerEntry[];
  events: RunProjectionEvent[];
  total_tokens: number;
  avg_tokens_per_sec: number;
}
