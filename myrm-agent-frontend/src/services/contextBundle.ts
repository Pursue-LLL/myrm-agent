/**
 * Context bundle API client (Harness volume + scene health).
 */

import { apiRequest } from '@/lib/api';

export interface ContextBundleSceneHealth {
  scene: string;
  path: string;
  index_status: 'ready' | 'degraded' | 'missing';
}

export interface ContextBundleHealth {
  bundle_id: string;
  schema_version: number;
  volume_layout_version: number;
  state_dir: string;
  memory_base_path: string;
  harness_dir: string;
  writable: boolean;
  manifest_exists: boolean;
  deploy_mode: string;
  storage_mode: string;
  scenes: ContextBundleSceneHealth[];
  migration_actions_pending: number;
  warnings: string[];
}

export async function getContextBundleHealth(): Promise<ContextBundleHealth> {
  return apiRequest<ContextBundleHealth>('/context-bundle');
}

export async function applyContextBundleMigration(): Promise<{ ok: boolean; manifest_exists: boolean }> {
  return apiRequest('/context-bundle/migrate/apply', { method: 'POST' });
}
