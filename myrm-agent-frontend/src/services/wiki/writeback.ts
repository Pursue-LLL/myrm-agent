/**
 * Wiki 5-layer writeback and review slip API client.
 *
 * [INPUT]
 * @/lib/api::apiRequest
 * ./service::buildWikiApiPath
 *
 * [OUTPUT]
 * DTOs: UsageLedgerRecord, ReviewSlipBatch, WritebackApplyRequest, WritebackApplyResult, WikiLayersStats
 * Functions: recordUsageLedger, generateReviewSlips, applyWritebackDecisions, getWikiLayersStats
 */

import { apiRequest } from '@/lib/api';
import { buildWikiApiPath } from './service';

export interface UsageLedgerItem {
  concept_or_path: string;
  contribution_type: 'referenced' | 'derived' | 'modified' | 'omitted';
  detail?: string;
}

export interface UsageLedgerRecord {
  task_id: string;
  title: string;
  executed_at: string;
  items: UsageLedgerItem[];
  deliverable_paths: string[];
}

export interface ReviewSlipOption {
  id: string;
  label: string;
  recommended: boolean;
  target_layer: 'methods' | 'claims' | 'deliverables_only' | 'discard';
}

export interface ReviewSlipQuestion {
  question_id: string;
  topic: string;
  candidate_content: string;
  rationale: string;
  options: ReviewSlipOption[];
  selected_option_id: string;
}

export interface ReviewSlipBatch {
  task_id: string;
  title: string;
  generated_at: string;
  questions: ReviewSlipQuestion[];
  excluded_matches_count: number;
}

export interface WritebackDecisionItem {
  question_id: string;
  selected_option_id: string;
  target_layer: 'methods' | 'claims' | 'deliverables_only' | 'discard';
  candidate_title: string;
  candidate_content: string;
}

export interface WritebackApplyRequest {
  task_id: string;
  decisions: WritebackDecisionItem[];
}

export interface WritebackApplyResult {
  task_id: string;
  committed_count: number;
  discarded_count: number;
  created_paths: string[];
  message: string;
}

export interface WikiLayersStats {
  agent_id: string;
  raw_files_count: number;
  sources_count: number;
  concepts_count: number;
  claims_count: number;
  methods_count: number;
  templates_count: number;
  deliverables_count: number;
  inbox_count: number;
}

export interface WikiLayerItem {
  slug: string;
  title: string;
  relative_path: string;
  publish_status: string;
  updated_at: string;
  content_snippet: string;
  source_task_id?: string;
  file_type?: 'markdown' | 'json';
}


export const writebackService = {
  async recordUsageLedger(record: UsageLedgerRecord, agentId?: string | null): Promise<{ status: string; saved_path: string }> {
    return apiRequest<{ status: string; saved_path: string }>(buildWikiApiPath('/wiki/writeback/ledger', agentId), {
      method: 'POST',
      body: JSON.stringify(record),
    });
  },

  async generateReviewSlips(
    payload: {
      task_id: string;
      task_title: string;
      candidate_insights: Array<{ topic: string; content: string; rationale?: string; recommended_layer?: string }>;
    },
    agentId?: string | null,
  ): Promise<ReviewSlipBatch> {
    return apiRequest<ReviewSlipBatch>(buildWikiApiPath('/wiki/writeback/review-slips', agentId), {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async applyWritebackDecisions(request: WritebackApplyRequest, agentId?: string | null): Promise<WritebackApplyResult> {
    return apiRequest<WritebackApplyResult>(buildWikiApiPath('/wiki/writeback/apply', agentId), {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  async getLayersStats(agentId?: string | null): Promise<WikiLayersStats> {
    return apiRequest<WikiLayersStats>(buildWikiApiPath('/wiki/writeback/layers-stats', agentId));
  },

  async getLayerItems(layer: string, agentId?: string | null, limit: number = 30): Promise<WikiLayerItem[]> {
    return apiRequest<WikiLayerItem[]>(
      buildWikiApiPath(`/wiki/writeback/layer-items?layer=${encodeURIComponent(layer)}&limit=${limit}`, agentId),
    );
  },
};

