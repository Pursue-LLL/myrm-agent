/**
 * Wiki 5-layer asset stats and layer item listing API client.
 *
 * [INPUT]
 * @/lib/api::apiRequest
 * ./service::buildWikiApiPath
 *
 * [OUTPUT]
 * DTOs: WikiLayersStats, WikiLayerItem
 * Functions: layersService.getLayersStats, getLayerItems
 */

import { apiRequest } from '@/lib/api';
import { buildWikiApiPath } from './service';

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
}

export const layersService = {
  async getLayersStats(agentId?: string | null): Promise<WikiLayersStats> {
    return apiRequest<WikiLayersStats>(buildWikiApiPath('/wiki/layers/stats', agentId));
  },

  async getLayerItems(layer: string, agentId?: string | null, limit: number = 30): Promise<WikiLayerItem[]> {
    return apiRequest<WikiLayerItem[]>(
      buildWikiApiPath(`/wiki/layers/items?layer=${encodeURIComponent(layer)}&limit=${limit}`, agentId),
    );
  },
};
