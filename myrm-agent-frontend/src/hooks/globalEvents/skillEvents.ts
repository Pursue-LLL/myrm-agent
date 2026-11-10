/**
 * [INPUT]
 * - ./skillGrowthToasts::showSkillLearnedToast / showSkillEvolvedToast (POS: 技能成长 toast)
 *
 * [OUTPUT]
 * - skillEventHandlers: 技能草稿 / 成长 / 进化事件的处理器表
 *
 * [POS]
 * 全局事件中与技能自我成长相关的部分：提示用户去审阅，并把事件转给技能页刷新自己。
 */
import { showSkillEvolvedToast, showSkillLearnedToast } from '@/hooks/globalEvents/skillGrowthToasts';

import type { GlobalEventDeps, GlobalEventHandler } from './eventTypes';

const SKILL_GROWTH_PATH = '/settings/evolutionPending';

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

export const skillEventHandlers: Record<string, GlobalEventHandler> = {
  new_skill_draft: handleNewSkillDraft,
  skill_growth_updated: handleSkillGrowthUpdated,
  skill_evolved: handleSkillEvolved,
};
