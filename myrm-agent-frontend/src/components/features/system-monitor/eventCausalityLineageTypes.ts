/**
 * [INPUT]: Event-driven causality records, DAG lineages, reverse file attribution results, and UI filter states.
 * [OUTPUT]: Strong TypeScript definitions for EventCausalityLineageDeck component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/eventCausalityLineageTypes.ts
 */

export type EventSourceKind = 'github_webhook' | 'slack_mention' | 'mcp_event' | 'cron' | string;

export type ArtifactChangeKind = 'created' | 'modified' | 'deleted' | string;

export interface ExternalEventTriggerItem {
  event_id: string;
  source_type: EventSourceKind;
  event_name: string;
  payload_summary: string;
  received_at_ms: number;
}

export interface CausalityRuleMatchItem {
  rule_id: string;
  rule_name: string;
  matched_condition: string;
}

export interface AgentActionNodeItem {
  action_id: string;
  agent_role: string;
  decision_rationale: string;
  tool_name: string;
  input_summary: string;
  duration_ms: number;
  tokens_consumed: number;
  timestamp_ms: number;
}

export interface ArtifactChangeRecordItem {
  file_path: string;
  change_type: ArtifactChangeKind;
  diff_summary: string;
  commit_sha: string;
  timestamp_ms: number;
}

export interface CausalityLineageRecordItem {
  causality_trace_id: string;
  session_id: string;
  trigger: ExternalEventTriggerItem;
  rule: CausalityRuleMatchItem;
  agent_role: string;
  actions: AgentActionNodeItem[];
  artifacts: ArtifactChangeRecordItem[];
  total_tokens: number;
  total_duration_ms: number;
  created_at_ms: number;
}

export interface FileAttributionResultItem {
  file_path: string;
  causality_trace_id: string;
  trigger_event_id: string;
  source_type: string;
  event_name: string;
  agent_role: string;
  change_record: ArtifactChangeRecordItem;
  rationale: string;
  occurred_at_ms: number;
}

export interface EventCausalityLineageDeckProps {
  lineages: CausalityLineageRecordItem[];
  selectedTraceId?: string;
  onSelectTrace?: (traceId: string) => void;
  onReverseLookupFile?: (filePath: string) => Promise<FileAttributionResultItem[]> | FileAttributionResultItem[];
  onRefresh?: () => void;
  isRefreshing?: boolean;
}
