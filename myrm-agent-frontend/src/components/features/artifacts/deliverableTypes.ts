/**
 * Deliverable Bundle & Manifest TypeScript Types.
 */

export type DeliverableCategory =
  | 'article'
  | 'social_post'
  | 'script'
  | 'data_sheet'
  | 'visual_asset'
  | 'report'
  | 'fact_check'
  | 'code_asset'
  | 'presentation'
  | 'other';

export interface DeliverableItem {
  id: string;
  relative_path: string;
  title: string;
  category: DeliverableCategory;
  vault_uri: string;
  sha256_hash?: string;
  size_bytes?: number;
  mime_type?: string;
  version_id?: string;
  description?: string;
  metadata?: Record<string, string>;
}

export interface DeliverableManifest {
  bundle_id: string;
  session_id: string;
  title: string;
  created_at: number;
  agent_id?: string;
  task_prompt?: string;
  items: DeliverableItem[];
  metadata?: Record<string, string>;
}

export type ConflictSeverity = 'critical' | 'warning' | 'info';
export type ResolutionStatus = 'resolved' | 'unresolved' | 'conditional';

export interface SourceClaim {
  source_uri: string;
  document_title: string;
  line_anchor?: string;
  claimed_value: string;
  snippet?: string;
  timestamp_hint?: string;
}

export interface FactCheckItem {
  id: string;
  claim_topic: string;
  severity: ConflictSeverity;
  status: ResolutionStatus;
  sources: SourceClaim[];
  adopted_value: string;
  resolution_rationale: string;
  confidence_score: number;
  affected_artifacts?: string[];
  metadata?: Record<string, string>;
}

export interface FactCheckSheet {
  sheet_id: string;
  session_id?: string;
  title: string;
  created_at: number;
  summary?: string;
  items: FactCheckItem[];
  metadata?: Record<string, string>;
}
