/**
 * [INPUT]: OpenTelemetry posture states, degrade status records, and probe callbacks.
 * [OUTPUT]: Strong TypeScript definitions for OpenTelemetry graceful degrade HUD and zero hard-dependency guarantees.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/otelDegradeTypes.ts
 */

export type OtelPostureState = 'ACTIVE' | 'DEGRADED_NO_OP' | 'DISABLED';

export interface OtelDegradeStatus {
  state: OtelPostureState;
  is_otel_installed: boolean;
  degrade_reason: string | null;
  intercepted_spans_count: number;
  intercepted_metrics_count: number;
  last_probe_time: string;
}

export interface OtelGracefulDegradeHUDProps {
  status: OtelDegradeStatus;
  onProbe?: () => void;
  onSimulateMissingToggle?: (simulate: boolean) => Promise<void> | void;
  isSimulating?: boolean;
}
