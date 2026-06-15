/**
 * External assistant skill migration staging and review client.
 *
 * [INPUT] lib/api::apiRequest (POS: authenticated HTTP client)
 * [OUTPUT] submit/list/approve/reject skill migration bundles
 * [POS] Frontend client for /migrations/skills/* and /migrations/pending/* review APIs.
 */

import { apiRequest } from '@/lib/api';

export interface SkillMigrationSubmitRequest {
  source: string;
  version?: string;
  skills: Record<string, unknown>[];
  description?: string | null;
  target_agent_id?: string | null;
}

export interface SkillMigrationSubmitResponse {
  migration_id: string;
  status: string;
  total_items: number;
}

export interface PendingMigrationItem {
  id: string;
  source: string;
  migration_type: string;
  summary: string;
  total_items: number;
  item_counts: Record<string, number>;
  status: string;
  created_at: string;
  target_agent_id?: string | null;
  target_agent_name?: string | null;
}

export interface PendingMigrationListResponse {
  items: PendingMigrationItem[];
  total: number;
}

export async function submitSkillMigration(body: SkillMigrationSubmitRequest): Promise<SkillMigrationSubmitResponse> {
  return apiRequest<SkillMigrationSubmitResponse>('/migrations/skills/submit', {
    method: 'POST',
    body: JSON.stringify({
      source: body.source,
      version: body.version ?? '1.0',
      skills: body.skills,
      description: body.description ?? null,
      target_agent_id: body.target_agent_id ?? null,
    }),
  });
}

export async function listPendingMigrations(limit = 50): Promise<PendingMigrationListResponse> {
  return apiRequest<PendingMigrationListResponse>(`/migrations/pending?limit=${limit}`);
}

export async function approvePendingMigration(migrationId: string): Promise<PendingMigrationItem> {
  return apiRequest<PendingMigrationItem>(`/migrations/pending/${migrationId}/approve`, {
    method: 'POST',
  });
}

export async function rejectPendingMigration(migrationId: string): Promise<PendingMigrationItem> {
  return apiRequest<PendingMigrationItem>(`/migrations/pending/${migrationId}/reject`, {
    method: 'POST',
  });
}
