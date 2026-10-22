/**
 * [INPUT]: Local span items, sink runtime status, and toggle/refresh callbacks.
 * [OUTPUT]: Strong TypeScript definitions for LoopForge OpenTelemetry optional local disk dashboard.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/localSinkTypes.ts
 */

export interface LocalSpanItem {
  trace_id: string;
  span_id: string;
  name: string;
  start_time_iso: string;
  end_time_iso: string;
  duration_ms: number;
  status: string;
  attributes: Record<string, string>;
}

export interface LocalSinkStatusData {
  is_enabled: boolean;
  sink_path: string;
  buffered_spans_count: number;
  persisted_spans_count: number;
  file_size_bytes: number;
  last_flush_iso: string | null;
}

export interface LoopForgeOtelOptionalDashboardProps {
  status: LocalSinkStatusData;
  spans: LocalSpanItem[];
  onToggleEnabled?: (enabled: boolean) => Promise<void> | void;
  onRefresh?: () => void;
  onSimulateSpan?: () => Promise<void> | void;
}
