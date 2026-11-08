/**
 * [INPUT] @/services/wikiService::{WikiSourceLevel, WikiSourceSnippet} (POS: Wiki 检索证据类型)
 * [OUTPUT] WikiStats: /wiki/stats 返回的知识库统计; WikiSnippetDrawerState: 证据抽屉的展示状态
 * [POS] Wiki 设置面板各模块共用的数据形状。
 */

import type { WikiSourceLevel, WikiSourceSnippet } from '@/services/wikiService';

export interface WikiStats {
  total_concepts: number;
  total_articles: number;
  total_raw_files: number;
  wiki_path: string;
  vault_ready: boolean;
  legacy_migrated: boolean;
  cognitive_index_ready: boolean;
  cognitive_log_entries: number;
  cognitive_hot_updated_at: string | null;
  structural_issues?: {
    broken_links: number;
    invalid_frontmatter_types: number;
    provenance_gaps: number;
    scanned_concepts: number;
  };
  asset_index?: {
    indexed: number;
    pending: number;
    failed: number;
    total_files: number;
    enabled: boolean;
  };
  synthesis_pending?: number;
  obsidian_launch_available?: boolean;
  vault_git_enabled?: boolean;
  vault_git_initialized?: boolean;
  vault_git_last_commit?: string | null;
  maintain_state?: {
    last_run_at: string | null;
    last_mode: string | null;
    last_issues_found: number;
    last_issues_fixed: number;
    last_connections_discovered: number;
    last_duration_ms: number;
    last_skipped_reason: string | null;
  };
  dedup_stats?: {
    duplicate_groups_pending: number;
    compile_jobs_prevented: number;
    eligible_raw_count: number;
    excluded_raw_count: number;
    trashed_raw_count: number;
    blocks_compile: boolean;
  };
}

export interface WikiSnippetDrawerState {
  open: boolean;
  title: string;
  section?: string;
  snippet: string;
  level?: WikiSourceLevel;
  snapshotStatus?: WikiSourceSnippet['snapshot_status'];
  claimStatus?: WikiSourceSnippet['claim_status'];
  claimConfidence?: WikiSourceSnippet['claim_confidence'];
  claimText?: WikiSourceSnippet['claim_text'];
  resourceUri?: string;
  supersededFromUri?: string;
  thumbnailUrl?: string | null;
}
