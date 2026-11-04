/**
 * Wiki 5-layer task usage ledger and layer inspection API client.
 *
 * [INPUT]
 * @/lib/api::apiRequest
 * ./service::buildWikiApiPath
 *
 * [OUTPUT]
 * DTOs: UsageLedgerItem, UsageLedgerRecord, WikiLayersStats, WikiLayerItem
 * Functions: writebackService.recordUsageLedger, getLayersStats, getLayerItems
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
  async recordUsageLedger(
    record: UsageLedgerRecord,
    agentId?: string | null,
  ): Promise<{ status: string; saved_path: string }> {
    return apiRequest<{ status: string; saved_path: string }>(buildWikiApiPath('/wiki/writeback/ledger', agentId), {
      method: 'POST',
      body: JSON.stringify(record),
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
