/**
 * [INPUT]
 * - ./skillGrowthToasts::showSkillLearnedToast / showSkillEvolvedToast (POS: 技能成长 toast)
 * - ./scheduleDebounced::scheduleDebounced (POS: 事件突发合并刷新)
 * - @/store/skill/useSkillStore (POS: 本地技能与启用配置，按需动态加载)
 *
 * [OUTPUT]
 * - skillEventHandlers: 技能草稿 / 成长 / 进化 / 技能池变更事件的处理器表
 *
 * [POS]
 * 全局事件中与技能相关的部分：提示用户去审阅，把事件转给技能页，并在技能池变化后刷新技能列表。
 */
import { showSkillEvolvedToast, showSkillLearnedToast } from '@/hooks/globalEvents/skillGrowthToasts';

import type { GlobalEventDeps, GlobalEventHandler } from './eventTypes';
import { scheduleDebounced } from './scheduleDebounced';

const SKILL_GROWTH_PATH = '/settings/evolutionPending';
/** Install, uninstall, sync and archive often arrive in bursts; one reload after the burst is enough. */
const SKILL_POOL_REFRESH_DELAY_MS = 300;

function skillGrowthOpener({ router }: GlobalEventDeps): () => void {
  return () => router.push(SKILL_GROWTH_PATH);
}

const handleNewSkillDraft: GlobalEventHandler = (payload, deps) => {
  const { t, pushToast } = deps;
  const name = String(payload.data.name ?? '');
  pushToast.info(t('newSkillDraft', { name }), {
    duration: 8_000,
    dismissible: true,
    action: {
      label: t('reviewDraft'),
      onClick: skillGrowthOpener(deps),
    },
  });
  window.dispatchEvent(
    new CustomEvent('skill-draft-created', {
      detail: {
        draftId: String(payload.data.draft_id ?? ''),
        name,
        draftType: String(payload.data.draft_type ?? ''),
      },
    }),
  );
};

const handleSkillGrowthUpdated: GlobalEventHandler = (payload, deps) => {
  const { t, pushToast } = deps;
  const openSkillGrowth = skillGrowthOpener(deps);
  const name = String(payload.data.name ?? '');
  const status = String(payload.data.status ?? '');

  if (status === 'AUTO_APPLIED') {
    showSkillLearnedToast(name, { t, pushToast, openSkillGrowth });
  } else if (status === 'FAILED_SCAN') {
    pushToast.error(t('skillGrowthFailedScan', { name }), {
      duration: 10_000,
      dismissible: true,
      action: {
        label: t('openSkillGrowth'),
        onClick: openSkillGrowth,
      },
    });
  } else if (status === 'BLOCKED_LOCKED') {
    pushToast.warning(t('skillGrowthBlockedLocked', { name }), {
      duration: 10_000,
      dismissible: true,
      action: {
        label: t('openSkillGrowth'),
        onClick: openSkillGrowth,
      },
    });
  }

  window.dispatchEvent(
    new CustomEvent('skill-growth-updated', {
      detail: {
        caseId: String(payload.data.case_id ?? ''),
        status,
        draftType: String(payload.data.draft_type ?? ''),
        name,
      },
    }),
  );
};

const handleSkillEvolved: GlobalEventHandler = (payload, deps) => {
  const { t, pushToast } = deps;
  const skillName = String(payload.data.skill_name ?? '');
  const evolutionType = String(payload.data.evolution_type ?? 'new');

  showSkillEvolvedToast(payload.data, { t, pushToast, openSkillGrowth: skillGrowthOpener(deps) });
  window.dispatchEvent(
    new CustomEvent('skill-evolved', {
      detail: { skill_name: skillName, evolution_type: evolutionType },
    }),
  );
};

const handleSkillPoolUpdated: GlobalEventHandler = (payload, { debouncedRefetches }) => {
  scheduleDebounced(debouncedRefetches, 'skill_pool_updated', SKILL_POOL_REFRESH_DELAY_MS, () => {
    import('@/store/skill/useSkillStore')
      .then(({ default: useSkillStore }) => {
        const { fetchLocalSkills, fetchUserSkillConfig } = useSkillStore.getState();
        void fetchLocalSkills();
        void fetchUserSkillConfig(true);
      })
      .catch(() => {});
  });
  window.dispatchEvent(new CustomEvent('skill_pool_updated', { detail: payload.data }));
};

export const skillEventHandlers: Record<string, GlobalEventHandler> = {
  new_skill_draft: handleNewSkillDraft,
  skill_growth_updated: handleSkillGrowthUpdated,
  skill_evolved: handleSkillEvolved,
  skill_pool_updated: handleSkillPoolUpdated,
};
