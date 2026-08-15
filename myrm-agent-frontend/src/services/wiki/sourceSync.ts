/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 * ./service::buildWikiApiPath (POS: Wiki API 路径构造)
 *
 * [OUTPUT]
 * WikiSourceSyncConfig/State/Status/ResultItem/RunSummary DTO 与源同步配置/状态/结果 API。
 *
 * [POS]
 * Wiki 源同步客户端。`/wiki/source-sync/*` REST 契约。
 */

import { apiRequest } from '@/lib/api';
import { buildWikiApiPath } from './service';

export interface WikiSourceSyncConfig {
  feishu_enabled: boolean;
  feishu_folder_token: string;
  gmail_enabled: boolean;
  gmail_label: string;
  gdrive_enabled: boolean;
  gdrive_folder_id: string;
  rss_feeds: string[];
  auto_compile: boolean;
  max_items_per_run: number;
  mirror_integrations_to_wiki: boolean;
}

export interface WikiSourceSyncSourceState {
  source: string;
  published: number;
  skipped: number;
  failed: number;
  errors: string[];
}

export interface WikiSourceSyncState {
  last_sync_at: string | null;
  last_errors: string[];
  sources: WikiSourceSyncSourceState[];
  total_published: number;
  total_skipped: number;
  total_failed: number;
}

export interface WikiSourceSyncStatus {
  config: WikiSourceSyncConfig;
  google_connected: boolean;
  google_drive_authorized: boolean;
  feishu_connected: boolean;
  state: WikiSourceSyncState;
}

export interface WikiSourceSyncResultItem {
  source: string;
  published: number;
  skipped: number;
  failed: number;
  errors: string[];
}

export interface WikiSourceSyncRunSummary {
  results: WikiSourceSyncResultItem[];
  total_published: number;
  total_skipped: number;
  total_failed: number;
}

export async function getWikiSourceSyncStatus(agentId?: string | null): Promise<WikiSourceSyncStatus> {
  return apiRequest<WikiSourceSyncStatus>(buildWikiApiPath('/wiki/sources/config', agentId));
}

export async function updateWikiSourceSyncConfig(
  patch: Partial<WikiSourceSyncConfig>,
  agentId?: string | null,
): Promise<WikiSourceSyncStatus> {
  return apiRequest<WikiSourceSyncStatus>(buildWikiApiPath('/wiki/sources/config', agentId), {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function syncWikiSources(agentId?: string | null): Promise<WikiSourceSyncRunSummary> {
  return apiRequest<WikiSourceSyncRunSummary>(buildWikiApiPath('/wiki/sources/sync', agentId), {
    method: 'POST',
  });
}
