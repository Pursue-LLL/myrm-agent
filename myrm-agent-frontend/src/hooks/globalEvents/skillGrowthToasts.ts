import { ApiError } from '@/lib/api';
import { updateSkillLifecycle } from '@/services/skill/core';
import type { toast } from '@/lib/utils/toast';

export type SkillGrowthTranslator = (key: string, values?: Record<string, string | number>) => string;

export interface SkillGrowthToastDeps {
  t: SkillGrowthTranslator;
  pushToast: { [K in 'success' | 'error']: (...args: Parameters<(typeof toast)[K]>) => void };
  openSkillGrowth: () => void;
}

const HTTP_CONFLICT = 409;

/**
 * Announces a skill the agent just learned in the background, with a one-click undo.
 * Undo archives the skill (reversible from the skill list) rather than deleting it, and
 * the server refuses when the skill is pinned or bound, so the failure copy tells the user why.
 */
export function showSkillLearnedToast(name: string, deps: SkillGrowthToastDeps): void {
  const { t, pushToast, openSkillGrowth } = deps;

  const undo = async () => {
    try {
      await updateSkillLifecycle(name, 'archive');
      pushToast.success(t('skillGrowthUndone', { name }));
    } catch (error) {
      const blocked = error instanceof ApiError && error.code === HTTP_CONFLICT;
      pushToast.error(t(blocked ? 'skillGrowthUndoBlocked' : 'skillGrowthUndoFailed', { name }));
    }
  };

  pushToast.success(t('skillEvolvedNew', { name }), {
    duration: 10_000,
    dismissible: true,
    action: { label: t('openSkillGrowth'), onClick: openSkillGrowth },
    cancel: { label: t('undoEvolve'), onClick: undo },
  });
}

/**
 * Announces an evolution that was applied directly (new skill approved by hand, or an opt-in
 * evolution patch). `notify === false` marks a learning already announced by its growth case,
 * so the UI refreshes through the dispatched event without a second toast.
 */
export function showSkillEvolvedToast(data: Record<string, unknown>, deps: SkillGrowthToastDeps): void {
  if (data.notify === false) {
    return;
  }

  const { t, pushToast, openSkillGrowth } = deps;
  const skillName = String(data.skill_name ?? '');
  const evolutionId = String(data.evolution_id ?? '');

  const rollback = async () => {
    try {
      const res = await fetch(`/api/v1/evolution/${evolutionId}/rollback`, { method: 'POST' });
      if (!res.ok) {
        throw new Error('Rollback failed');
      }
      pushToast.success(t('rollbackSuccess', { name: skillName }));
    } catch {
      pushToast.error(t('rollbackFailed', { name: skillName }));
    }
  };

  pushToast.success(
    String(data.evolution_type ?? 'new') === 'new'
      ? t('skillEvolvedNew', { name: skillName })
      : t('skillEvolvedPatch', { name: skillName }),
    {
      description: String(data.description ?? ''),
      duration: 8_000,
      dismissible: true,
      action: { label: t('openSkillGrowth'), onClick: openSkillGrowth },
      cancel: evolutionId ? { label: t('undoEvolve'), onClick: rollback } : undefined,
    },
  );
}
