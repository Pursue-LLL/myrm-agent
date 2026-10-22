/**
 * [INPUT]: Authoritative resource access telemetry, in-conversation audit timeline events, and SHA-256 digests.
 * [OUTPUT]: Strong TypeScript definitions for InConversationAuditTheaterDeck component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/auditTheaterTypes.ts
 */

export type ResourceAccessKindType = 'file' | 'memory' | 'connector_mcp' | 'web_network';
export type ResourceAccessModeType = 'read' | 'write' | 'execute';

export interface ResourceAccessEntryItem {
  entry_id: string;
  session_id: string;
  resource_id: string;
  kind: ResourceAccessKindType;
  mode: ResourceAccessModeType;
  scope_detail: string;
  size_bytes: number;
  line_count: number;
  success: boolean;
  timestamp_ms: number;
}

export interface TimelineAuditEventItem {
  event_id: string;
  session_id: string;
  step_name: string;
  tool_name: string;
  is_plan: boolean;
  status: string;
  duration_ms: number;
  inputs_summary: string;
  timestamp_ms: number;
}

export interface SessionDataAccessLedgerItem {
  session_id: string;
  resources: ResourceAccessEntryItem[];
  events: TimelineAuditEventItem[];
  total_resources_accessed: number;
  total_files_read: number;
  total_files_written: number;
  total_memories_queried: number;
  total_network_domains_visited: number;
  lie_immune_verified: boolean;
  digest_sha256: string;
  generated_at_ms: number;
}

export interface InConversationAuditTheaterDeckProps {
  ledger: SessionDataAccessLedgerItem;
  onRefresh?: () => Promise<void> | void;
  isLoading?: boolean;
  className?: string;
}
