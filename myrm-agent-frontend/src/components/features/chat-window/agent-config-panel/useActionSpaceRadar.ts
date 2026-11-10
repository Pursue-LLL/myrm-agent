import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';

import { toast } from '@/hooks/shared/useToast';
import { getApiUrl } from '@/lib/api';
import { runCuratorSweep } from '@/services/skill';
import type { BuiltinToolId } from '@/store/chat/types';
import type { Skill } from '@/store/skill/types';
import type { AgentSkillConfigMap } from '@/types/agentSkillConfig';

import type { Turn1CatalogPreview } from './ActionSpaceAccuracyRadar';

/** 用户停手这么久才向服务端估算：连续勾选只估算最后一次。 */
const ESTIMATE_DEBOUNCE_MS = 500;

/** 服务端还没回答时雷达显示的初值：行动空间不拥挤。 */
const NO_ESTIMATE = {
  accuracyLevel: 100,
  actionSpaceScore: 0,
  maxSafeScore: 1500,
  isNoiseHigh: false,
  isNoiseCritical: false,
};

interface EstimateResponse {
  data?: {
    accuracy_level: number;
    ascs_score: number;
    max_safe_score: number;
    is_high: boolean;
    is_critical: boolean;
    catalog_preview?: unknown;
  };
}

interface ActionSpaceRadarOptions {
  /** 当前卡片不展示估算时不向服务端请求。 */
  estimate: boolean;
  enabledSkills: Skill[];
  skillIds: string[];
  skillConfigs: AgentSkillConfigMap;
  mcpNames: string[];
  builtinTools: BuiltinToolId[];
  onRefreshSkills?: () => Promise<void>;
}

/** 服务端的目录预览缺任何一项都不展示，避免雷达渲染半截数据。 */
function isCatalogPreview(value: unknown): value is Turn1CatalogPreview {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const preview = value as Record<string, unknown>;
  return (
    typeof preview.inline_count === 'number' &&
    typeof preview.hidden_count === 'number' &&
    typeof preview.overflow_count === 'number' &&
    typeof preview.catalog_tokens === 'number' &&
    typeof preview.search_mounted === 'boolean'
  );
}

/**
 * 行动空间雷达：向服务端估算草稿的行动空间拥挤度，并清理已过期的核心技能。
 *
 * 估算以请求体为标识：草稿内容不变就不重新请求，较早发出的请求在草稿变化后被中止，它的迟到应答不会覆盖新结果。
 */
export function useActionSpaceRadar({
  estimate,
  enabledSkills,
  skillIds,
  skillConfigs,
  mcpNames,
  builtinTools,
  onRefreshSkills,
}: ActionSpaceRadarOptions) {
  const tPanel = useTranslations('agent.configPanel');
  const [estimateResult, setEstimateResult] = useState(NO_ESTIMATE);
  const [catalogPreview, setCatalogPreview] = useState<Turn1CatalogPreview | null>(null);
  const [answeredBody, setAnsweredBody] = useState<string | null>(null);
  const [isSmartPruning, setIsSmartPruning] = useState(false);

  const requestBody = useMemo(
    () =>
      JSON.stringify({
        skill_ids: skillIds,
        skill_configs: skillConfigs,
        mcp_servers: mcpNames,
        enabled_builtin_tools: builtinTools,
      }),
    [skillIds, skillConfigs, mcpNames, builtinTools],
  );

  useEffect(() => {
    if (!estimate) {
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(getApiUrl('/user-agents/evaluate-action-space'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: requestBody,
          signal: controller.signal,
        });
        if (!response.ok) {
          return;
        }
        const resData: EstimateResponse = await response.json();
        if (controller.signal.aborted || !resData.data) {
          return;
        }
        setEstimateResult({
          accuracyLevel: resData.data.accuracy_level,
          actionSpaceScore: resData.data.ascs_score,
          maxSafeScore: resData.data.max_safe_score,
          isNoiseHigh: resData.data.is_high,
          isNoiseCritical: resData.data.is_critical,
        });
        setCatalogPreview(isCatalogPreview(resData.data.catalog_preview) ? resData.data.catalog_preview : null);
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error('Failed to evaluate action space', error);
        }
      } finally {
        if (!controller.signal.aborted) {
          setAnsweredBody(requestBody);
        }
      }
    }, ESTIMATE_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [estimate, requestBody]);

  const isEvaluating = estimate && answeredBody !== requestBody;
  const { actionSpaceScore, maxSafeScore } = estimateResult;
  const noiseLevel = Math.min(100, Math.round((actionSpaceScore / maxSafeScore) * 100));

  const staleCoreSkills = useMemo(
    () =>
      skillIds.filter((id) => {
        if (!(skillConfigs[id]?.is_core ?? false)) {
          return false;
        }
        return enabledSkills.find((skill) => skill.id === id)?.usage_stats?.lifecycle_status === 'stale';
      }),
    [skillIds, skillConfigs, enabledSkills],
  );

  const handleSmartPrune = useCallback(async () => {
    if (isSmartPruning) {
      return;
    }
    setIsSmartPruning(true);
    try {
      toast({ title: tPanel('actionSpaceRadar.smartPruneRunning') });
      const result = await runCuratorSweep();
      toast({
        title: tPanel('actionSpaceRadar.smartPruneSuccess', {
          stale: result.stale_count,
          archived: result.archived_count,
        }),
      });
      if (onRefreshSkills) {
        await onRefreshSkills();
      }
    } catch (error) {
      console.error('Curator sweep failed', error);
      toast({ title: tPanel('actionSpaceRadar.smartPruneFailed'), variant: 'destructive' });
    } finally {
      setIsSmartPruning(false);
    }
  }, [isSmartPruning, onRefreshSkills, tPanel]);

  return {
    ...estimateResult,
    noiseLevel,
    catalogPreview,
    isEvaluating,
    staleCoreSkills,
    isSmartPruning,
    handleSmartPrune,
  };
}
