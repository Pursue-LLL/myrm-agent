import type { Skill } from '@/store/skill/types';

export const GOOGLE_WORKSPACE_SKILL_ID = 'google-workspace';

export function isGoogleWorkspaceOAuthUnavailable(skill: Skill): boolean {
  return skill.id === GOOGLE_WORKSPACE_SKILL_ID && !skill.available;
}

type SkillsCardTranslator = (
  key: 'card.integrationOAuth.googleWorkspace.unavailable' | 'card.unavailable',
) => string;

export function getSkillUnavailableDisplayMessage(skill: Skill, t: SkillsCardTranslator): string {
  if (isGoogleWorkspaceOAuthUnavailable(skill)) {
    return t('card.integrationOAuth.googleWorkspace.unavailable');
  }
  return skill.unavailable_reason || t('card.unavailable');
}

export const SETTINGS_GOOGLE_OAUTH_PATH = '/settings/credentials';
