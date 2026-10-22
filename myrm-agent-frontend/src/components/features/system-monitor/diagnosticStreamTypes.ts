/**
 * [INPUT]: Diagnostic events, severity, category filters, and dual-track stream status.
 * [OUTPUT]: Strong TypeScript definitions for RunStream diagnostic drawer and chat stream anti-pollution.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/diagnosticStreamTypes.ts
 */

export type DiagnosticSeverity = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

export type DiagnosticCategory =
  | 'RETRY'
  | 'CONTEXT_TRUNCATION'
  | 'MCP_LATENCY'
  | 'SANDBOX_PRESSURE'
  | 'MODEL_DEGRADE'
  | 'CUSTOM';

export interface DiagnosticEventItem {
  event_id: string;
  session_id: string;
  run_id: string;
  category: DiagnosticCategory;
  severity: DiagnosticSeverity;
  code: string;
  message: string;
  details: Record<string, string>;
  timestamp: string;
}

export interface DiagnosticStreamStatsData {
  total_events: number;
  by_severity: Record<DiagnosticSeverity, number>;
  by_category: Record<DiagnosticCategory, number>;
}

export interface RunStreamDiagnosticDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId?: string;
  runId?: string;
  events: DiagnosticEventItem[];
  stats?: DiagnosticStreamStatsData;
  onRefresh?: () => void;
  onFilterSeverity?: (severity: DiagnosticSeverity | 'ALL') => void;
  onFilterCategory?: (category: DiagnosticCategory | 'ALL') => void;
}
