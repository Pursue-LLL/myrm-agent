/**
 * [INPUT]
 * - lib/api::apiRequest (POS: authenticated API client)
 *
 * [OUTPUT]
 * - getContextBundleHealth, applyContextBundleMigration
 *
 * [POS]
 * Context bundle health API client for Developer System Health panel.
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

export interface ContextBundleMigrationResult {
  ok: boolean;
  bundle_id: string;
  schema_version: number;
  writable: boolean;
  manifest_exists: boolean;
  actions: string[];
  warnings: string[];
}

export async function getContextBundleHealth(): Promise<ContextBundleHealth> {
  return apiRequest<ContextBundleHealth>('/api/context-bundle');
}

export async function applyContextBundleMigration(): Promise<ContextBundleMigrationResult> {
  return apiRequest<ContextBundleMigrationResult>('/api/context-bundle/migrate/apply', {
    method: 'POST',
  });
}
