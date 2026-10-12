'use client';

import { memo } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { AlertTriangle } from 'lucide-react';
import {
  getIntegrationSkillSettingsLinkLabel,
  getIntegrationSkillSettingsPath,
  getSkillUnavailableDisplayMessage,
  hasIntegrationSettingsLink,
  isEnvGatedSkillUnavailable,
} from '@/lib/skills/integrationOAuthDisplay';
import type { Skill } from '@/store/skill/types';

const ACTION_CLASS =
  'shrink-0 text-xs font-medium underline underline-offset-2 hover:text-amber-700 dark:hover:text-amber-300';

interface SkillAvailabilityNoticeProps {
  skill: Skill;
  /** Opens the skill detail sheet, where its API keys are entered. */
  onConfigureKeys?: () => void;
}

/** Why a skill card is unavailable, with the one action that unblocks it. */
const SkillAvailabilityNotice = memo(({ skill, onConfigureKeys }: SkillAvailabilityNoticeProps) => {
  const t = useTranslations('settings.skills');

  if (skill.available || !(skill.unavailable_reason || hasIntegrationSettingsLink(skill))) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1 mt-1 text-xs text-amber-600 dark:text-amber-400 sm:flex-row sm:items-center sm:gap-2">
      <div className="flex items-center gap-1 min-w-0">
        <AlertTriangle size={12} className="shrink-0" />
        <span className="truncate">{getSkillUnavailableDisplayMessage(skill, t)}</span>
      </div>
      {hasIntegrationSettingsLink(skill) && (
        <Link
          href={getIntegrationSkillSettingsPath(skill)}
          className={ACTION_CLASS}
          onClick={(e) => e.stopPropagation()}
        >
          {getIntegrationSkillSettingsLinkLabel(skill, t)}
        </Link>
      )}
      {onConfigureKeys && isEnvGatedSkillUnavailable(skill) && (
        <button
          type="button"
          className={ACTION_CLASS}
          onClick={(e) => {
            e.stopPropagation();
            onConfigureKeys();
          }}
        >
          {t('card.integrationOAuth.envSkill.configureInSettings')}
        </button>
      )}
    </div>
  );
});

SkillAvailabilityNotice.displayName = 'SkillAvailabilityNotice';

export default SkillAvailabilityNotice;
