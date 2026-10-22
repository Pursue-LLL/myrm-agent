/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * 版本列表/对比/回滚、资源包修订恢复、skill_manage 批次撤销 `/mutations/{id}/rollback` 封装。
 *
 * [POS]
 * 技能优化客户端。`/skill-optimization/*` REST 契约。
 */

import { apiRequest } from '@/lib/api';

const PREFIX = '/skill-optimization';

export interface SkillVersionSummary {
  version: number;
  created_at: string;
  created_by: string;
  is_active: boolean;
  optimization_id: string | null;
}

export interface SkillVersionsResponse {
  skill_id: string;
  total: number;
  versions: SkillVersionSummary[];
}

export interface SkillVersionCompareResponse {
  skill_id: string;
  v1: { version: number; content: string };
  v2: { version: number; content: string };
  content_changed: boolean;
}

export interface SkillVersionDetailResponse {
  skill_id: string;
  version: number;
  content: string;
  is_active: boolean;
}

export async function listSkillVersions(skillId: string, limit = 20): Promise<SkillVersionsResponse> {
  return apiRequest<SkillVersionsResponse>(`${PREFIX}/versions/${encodeURIComponent(skillId)}?limit=${limit}`);
}

export async function getSkillVersionDetail(skillId: string, version: number): Promise<SkillVersionDetailResponse> {
  return apiRequest<SkillVersionDetailResponse>(`${PREFIX}/versions/${encodeURIComponent(skillId)}/${version}`);
}

export interface SkillPackageRevisionSummary {
  revision_number: number;
  revision_id: string;
  created_by: string;
  resource_paths: string[];
}

export async function listSkillPackageRevisions(
  skillId: string,
  limit = 20,
): Promise<{ skill_id: string; revisions: SkillPackageRevisionSummary[] }> {
  return apiRequest(`${PREFIX}/package-revisions/${encodeURIComponent(skillId)}?limit=${limit}`);
}

export async function restoreSkillPackageRevision(
  skillId: string,
  revisionNumber: number,
): Promise<{ status: string; revision_number: number }> {
  return apiRequest(
    `${PREFIX}/package-revisions/${encodeURIComponent(skillId)}/restore/${revisionNumber}`,
    { method: 'POST' },
  );
}

export async function rollbackSkillVersion(skillId: string, targetVersion: number): Promise<{ to_version: number }> {
  return apiRequest<{ to_version: number }>(
    `${PREFIX}/rollback/${encodeURIComponent(skillId)}?target_version=${targetVersion}`,
    { method: 'POST' },
  );
}

export async function compareSkillVersions(
  skillId: string,
  v1: number,
  v2: number,
): Promise<SkillVersionCompareResponse> {
  return apiRequest<SkillVersionCompareResponse>(
    `${PREFIX}/versions/${encodeURIComponent(skillId)}/compare?v1=${v1}&v2=${v2}`,
  );
}

export async function rollbackSkillMutationBatch(batchId: string): Promise<{
  batch_id: string;
  skills_restored: number;
  status: string;
}> {
  return apiRequest<{
    batch_id: string;
    skills_restored: number;
    status: string;
  }>(`${PREFIX}/mutations/${encodeURIComponent(batchId)}/rollback`, {
    method: 'POST',
    // Every caller words the failure itself (e.g. "already undone"); the generic toast would be a second one.
    silent: true,
  });
}
