/**
 * [INPUT]: None (Raw types for sanitized debug bundle and ephemeral share link).
 * [OUTPUT]: Strong TypeScript definitions for Zero-Leak debug package, audit trails, and self-destruct links.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/sanitizedDebugTypes.ts
 */

export interface SystemVitals {
  os_name: string;
  python_version: string;
  cpu_cores: number;
  memory_total_gb: number;
  network_connectivity: string;
  timestamp: string;
}

export interface RedactionAudit {
  rule_type: string;
  masked_placeholder: string;
  occurrences_count: number;
}

export interface SanitizedDebugDump {
  dump_id: string;
  vitals: SystemVitals;
  sanitized_logs: string[];
  recent_traces: Record<string, string>[];
  redacted_audits: RedactionAudit[];
  total_redacted_count: number;
  user_note: string;
  checksum_sha256: string;
  created_at: string;
}

export interface EphemeralShareLink {
  share_token: string;
  dump_id: string;
  share_url: string;
  expires_at: string;
  max_views: number;
  remaining_views: number;
  is_destroyed: boolean;
  created_at: string;
}

export interface ConsumeShareResult {
  dump: SanitizedDebugDump | null;
  remaining_views: number;
  is_destroyed: boolean;
  error?: string | null;
}
