/**
 * [INPUT]
 * - None (pure TypeScript contract types)
 *
 * [OUTPUT]
 * - ReconnectStatus, SessionAtomicSnapshot, LiveStreamFilterConfig, LiveDeltaEvent, ReconnectMetrics
 *
 * [POS]
 * Client-side type definitions for Atomic Snapshot and Live Stream Zero-Replay Reconnect Protocol (Item 36 P0).
 * Implements earendil-works/pi harness-v2 UI model specifications.
 */

export type ReconnectStatus =
  | 'idle'
  | 'fetching_snapshot'
  | 'subscribing_live'
  | 'connected'
  | 'reconnecting'
  | 'disconnected';

export interface ActiveToolCallSnapshot {
  id?: string;
  tool_name?: string;
  status?: string;
}

export interface ArtifactSummarySnapshot {
  id?: string;
  name?: string;
  status?: string;
}

export interface SessionAtomicSnapshot {
  session_id: string;
  epoch_id: string;
  state_version: number;
  snapshot_timestamp_ms: number;
  status: 'idle' | 'running' | 'paused' | 'interrupted' | 'error';
  leaf_entry_id: string | null;
  active_tool_calls: ActiveToolCallSnapshot[];
  message_count: number;
  latest_turn_summary: string | null;
  artifacts_summary: ArtifactSummarySnapshot[];
  metadata: Record<string, string>;
}

export interface LiveStreamFilterConfig {
  client_snapshot_timestamp_ms: number;
  client_state_version: number;
  allow_equal_timestamp?: boolean;
}

export interface LiveDeltaEvent {
  type: string;
  state_version?: number;
  status?: 'idle' | 'running' | 'paused' | 'interrupted' | 'error';
  message_count?: number;
  server_time_ms?: number;
  [key: string]: unknown;
}

export interface ReconnectMetrics {
  lastSnapshotAtMs: number | null;
  lastEventAtMs: number | null;
  reconnectCount: number;
  latencyMs: number;
}
