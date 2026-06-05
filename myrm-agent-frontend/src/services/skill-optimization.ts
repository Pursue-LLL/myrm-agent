import { apiRequest } from '@/lib/api';

const PREFIX = '/skill-optimization';

export interface SkillQualityScore {
  success_rate: number;
  token_efficiency: number;
  execution_time: number;
  user_satisfaction: number;
  call_frequency: number;
  overall_score: number;
}

export interface QualityHistoryPoint {
  timestamp: string;
  quality_score: SkillQualityScore;
}

export interface OptimizationRecommendation {
  skill_id: string;
  skill_name: string;
  priority_score: number;
  reasons: string[];
  last_optimized_at: string | null;
  current_quality: number;
}

export interface InsightsSummary {
  days: number;
  summary: {
    active_skills: number;
    total_calls: number;
    success_rate: number;
    avg_duration_seconds: number;
    top_skill_id: string;
  };
}

export async function getSkillQualityHistory(skillId: string, days: number = 30): Promise<QualityHistoryPoint[]> {
  return apiRequest<QualityHistoryPoint[]>(`${PREFIX}/quality-history?skill_id=${skillId}&days=${days}`);
}

export async function getInsightsSummary(days: number = 7): Promise<InsightsSummary> {
  return apiRequest<InsightsSummary>(`${PREFIX}/insights/summary?days=${days}`);
}

export async function getRecommendations(
  limit: number = 10,
): Promise<{ total_recommendations: number; recommendations: OptimizationRecommendation[] }> {
  return apiRequest<{
    total_recommendations: number;
    recommendations: OptimizationRecommendation[];
  }>(`${PREFIX}/recommendations?limit=${limit}`);
}

export async function triggerBatchOptimization(
  skillIds: string[],
  maxConcurrent: number = 3,
): Promise<{ batch_task_id: string; message: string }> {
  return apiRequest<{ batch_task_id: string; message: string }>(`${PREFIX}/batch-optimize`, {
    method: 'POST',
    body: JSON.stringify({ skill_ids: skillIds, max_concurrent: maxConcurrent, priority: 1 }),
  });
}

export interface SkillVersionSummary {
  version: number;
  created_at: string;
  created_by: string;
  is_active: boolean;
  optimization_id: string | null;
  quality_score: SkillQualityScore | null;
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

export async function listSkillVersions(skillId: string, limit = 20): Promise<SkillVersionsResponse> {
  return apiRequest<SkillVersionsResponse>(`${PREFIX}/versions/${encodeURIComponent(skillId)}?limit=${limit}`);
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
