import type { Skill } from '@/store/skill/types';

export const GOOGLE_WORKSPACE_SKILL_ID = 'google-workspace';
export const X_LIVE_SEARCH_SKILL_ID = 'x-live-search';
export const NOTION_WORKSPACE_SKILL_ID = 'notion-workspace';
export const LINEAR_PROJECT_SKILL_ID = 'linear-project';
export const XURL_SKILL_ID = 'xurl';

export const SETTINGS_GOOGLE_OAUTH_PATH = '/settings/credentials';
export const SETTINGS_PROVIDERS_PATH = '/settings/models';
export const SETTINGS_SKILLS_PATH = '/settings/skills';

type SkillsCardTranslator = (
  key:
    | 'card.integrationOAuth.googleWorkspace.unavailable'
    | 'card.integrationOAuth.googleWorkspace.connectInSettings'
    | 'card.integrationOAuth.xLiveSearch.unavailable'
    | 'card.integrationOAuth.xLiveSearch.connectInSettings'
    | 'card.integrationOAuth.envSkill.unavailable'
    | 'card.integrationOAuth.envSkill.configureInSettings'
    | 'card.integrationOAuth.xurl.unavailable'
    | 'card.unavailable',
) => string;

export function isGoogleWorkspaceOAuthUnavailable(skill: Skill): boolean {
  return skill.id === GOOGLE_WORKSPACE_SKILL_ID && !skill.available;
}

export function isXLiveSearchUnavailable(skill: Skill): boolean {
  return skill.id === X_LIVE_SEARCH_SKILL_ID && !skill.available;
}

export function isEnvGatedSkillUnavailable(skill: Skill): boolean {
  return (
    (skill.id === NOTION_WORKSPACE_SKILL_ID || skill.id === LINEAR_PROJECT_SKILL_ID) && !skill.available
  );
}

export function isXurlBinUnavailable(skill: Skill): boolean {
  return skill.id === XURL_SKILL_ID && !skill.available;
}

export function hasIntegrationSettingsLink(skill: Skill): boolean {
  return (
    isGoogleWorkspaceOAuthUnavailable(skill) ||
    isXLiveSearchUnavailable(skill) ||
    isEnvGatedSkillUnavailable(skill)
  );
}

export function getIntegrationSkillSettingsPath(skill: Skill): string {
  if (isGoogleWorkspaceOAuthUnavailable(skill)) {
    return SETTINGS_GOOGLE_OAUTH_PATH;
  }
  if (isXLiveSearchUnavailable(skill)) {
    return SETTINGS_PROVIDERS_PATH;
  }
  return SETTINGS_SKILLS_PATH;
}

export function getIntegrationSkillSettingsLinkLabel(skill: Skill, t: SkillsCardTranslator): string {
  if (isGoogleWorkspaceOAuthUnavailable(skill)) {
    return t('card.integrationOAuth.googleWorkspace.connectInSettings');
  }
  if (isXLiveSearchUnavailable(skill)) {
    return t('card.integrationOAuth.xLiveSearch.connectInSettings');
  }
  return t('card.integrationOAuth.envSkill.configureInSettings');
}

export function getSkillUnavailableDisplayMessage(skill: Skill, t: SkillsCardTranslator): string {
  if (isGoogleWorkspaceOAuthUnavailable(skill)) {
    return t('card.integrationOAuth.googleWorkspace.unavailable');
  }
  if (isXLiveSearchUnavailable(skill)) {
    return t('card.integrationOAuth.xLiveSearch.unavailable');
  }
  if (isEnvGatedSkillUnavailable(skill)) {
    return t('card.integrationOAuth.envSkill.unavailable');
  }
  if (isXurlBinUnavailable(skill)) {
    return t('card.integrationOAuth.xurl.unavailable');
  }
  return skill.unavailable_reason || t('card.unavailable');
}
