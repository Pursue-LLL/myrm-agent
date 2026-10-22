/**
 * [INPUT]: Context chunk sources, SHA256 fingerprints, token breakdown, and diff items.
 * [OUTPUT]: Strong TypeScript definitions for turn context provenance and reproducibility audit modal.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/turnContextProvenanceTypes.ts
 */

export type InjectionSourceKind =
  | 'system_prompt'
  | 'memory'
  | 'skill'
  | 'mcp_server'
  | 'workspace_file'
  | 'tool_schema';

export type DiffType = 'ADDED' | 'REMOVED' | 'MODIFIED' | 'UNCHANGED';

export interface TurnContextChunkItem {
  chunk_id: string;
  source_id: string;
  kind: InjectionSourceKind;
  content_sha256: string;
  content_chars: number;
  estimated_tokens: number;
  order_index: number;
  meta: Record<string, string>;
}

export interface TurnContextInjectionManifest {
  session_id: string;
  turn_id: string;
  chunks: TurnContextChunkItem[];
  total_tokens: number;
  total_chars: number;
  model_snapshot_id: string;
  created_at: string;
}

export interface TurnProvenanceDiffItem {
  source_id: string;
  kind: InjectionSourceKind;
  diff_type: DiffType;
  previous_sha256?: string | null;
  current_sha256?: string | null;
  token_delta: number;
}

export interface SourceTokenBreakdownItem {
  kind: string;
  tokens: number;
  percentage: number;
  chunk_count: number;
}

export interface TurnTokenBreakdown {
  session_id: string;
  turn_id: string;
  total_tokens: number;
  breakdown_by_kind: Record<string, SourceTokenBreakdownItem>;
}
