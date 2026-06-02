'use client';

import { useCallback, useState } from 'react';
import { apiRequest, showApiError } from '@/lib/api';

interface QualityScore {
  overall_score: number;
  success_rate: number;
  token_efficiency: number;
  execution_time: number;
  user_satisfaction: number;
  call_frequency: number;
}

export interface SkillVersionSummary {
  version: number;
  created_at: string;
  created_by: string;
  is_active: boolean;
  optimization_id: string | null;
  quality_score: QualityScore | null;
  metadata: Record<string, unknown> | null;
}

export interface SkillVersionDetail extends SkillVersionSummary {
  skill_id: string;
  content: string;
}

interface VersionListResponse {
  skill_id: string;
  total: number;
  versions: SkillVersionSummary[];
}

interface CompareResponse {
  skill_id: string;
  v1: SkillVersionDetail;
  v2: SkillVersionDetail;
  score_delta: Record<string, number> | null;
  content_changed: boolean;
}

interface RollbackResponse {
  message: string;
  skill_id: string;
  from_version: number | null;
  to_version: number;
}

export function useSkillVersions(skillId: string) {
  const [versions, setVersions] = useState<SkillVersionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  const fetchVersions = useCallback(
    async (limit = 50) => {
      if (!skillId) return;
      setLoading(true);
      try {
        const data = await apiRequest<VersionListResponse>(`/skill-optimization/versions/${skillId}?limit=${limit}`);
        setVersions(data.versions);
        setTotal(data.total);
      } catch (error) {
        showApiError(error);
      } finally {
        setLoading(false);
      }
    },
    [skillId],
  );

  const getVersionDetail = useCallback(
    async (version: number): Promise<SkillVersionDetail | null> => {
      try {
        return await apiRequest<SkillVersionDetail>(`/skill-optimization/versions/${skillId}/${version}`);
      } catch (error) {
        showApiError(error);
        return null;
      }
    },
    [skillId],
  );

  const compareVersions = useCallback(
    async (v1: number, v2: number): Promise<CompareResponse | null> => {
      try {
        return await apiRequest<CompareResponse>(`/skill-optimization/versions/${skillId}/compare?v1=${v1}&v2=${v2}`);
      } catch (error) {
        showApiError(error);
        return null;
      }
    },
    [skillId],
  );

  const rollbackToVersion = useCallback(
    async (targetVersion: number): Promise<RollbackResponse | null> => {
      try {
        const result = await apiRequest<RollbackResponse>(
          `/skill-optimization/rollback/${skillId}?target_version=${targetVersion}`,
          { method: 'POST' },
        );
        await fetchVersions();
        return result;
      } catch (error) {
        showApiError(error);
        return null;
      }
    },
    [skillId, fetchVersions],
  );

  return {
    versions,
    total,
    loading,
    fetchVersions,
    getVersionDetail,
    compareVersions,
    rollbackToVersion,
  };
}
