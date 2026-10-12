import type { Skill } from '@/store/skill/types';

export const GOOGLE_WORKSPACE_SKILL_ID = 'google-workspace';
export const X_LIVE_SEARCH_SKILL_ID = 'x-live-search';
export const XURL_SKILL_ID = 'xurl';

export const SETTINGS_GOOGLE_OAUTH_PATH = '/settings/credentials';
export const SETTINGS_PROVIDERS_PATH = '/settings/models';
export const SETTINGS_DEFAULT_MODEL_PATH = '/settings/defaultModel';
export const SETTINGS_AGENTS_LOADOUT_PATH = '/settings/agents#loadout';
export const SETTINGS_SKILLS_PATH = '/settings/skills';

type SkillsCardTranslator = (
  key:
    | 'card.integrationOAuth.googleWorkspace.unavailable'
    | 'card.integrationOAuth.googleWorkspace.connectInSettings'
    | 'card.integrationOAuth.connectionRequired.unavailable'
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

/**
 * A skill whose only declared requirement is env keys (e.g. an API key) and is unavailable can only be
 * unblocked by saving those keys, which is done in the skill detail sheet itself — so this is an in-place
 * action, not a settings link. Mixed bins/config requirements fall back to the server-provided reason.
 */
export function isEnvGatedSkillUnavailable(skill: Skill): boolean {
  const { bins, env, config } = skill.requires;
  return !skill.available && env.length > 0 && bins.length === 0 && config.length === 0;
}

export function isXurlBinUnavailable(skill: Skill): boolean {
  return skill.id === XURL_SKILL_ID && !skill.available;
}

/** An unavailable skill that waits on an account or connector, which can only be connected in settings. */
function isIntegrationConnectionMissing(skill: Skill): boolean {
  const hasRequiredAccounts = (skill.required_oauth_issuers?.length ?? 0) > 0;
  const hasRequiredConnectors = (skill.required_mcp_server_ids?.length ?? 0) > 0;
  return !skill.available && (hasRequiredAccounts || hasRequiredConnectors);
}

export function hasIntegrationSettingsLink(skill: Skill): boolean {
  return (
    isIntegrationConnectionMissing(skill) || isGoogleWorkspaceOAuthUnavailable(skill) || isXLiveSearchUnavailable(skill)
  );
}

export function getIntegrationSkillSettingsPath(skill: Skill): string {
  if (skill.required_mcp_server_ids && skill.required_mcp_server_ids.length > 0 && !skill.available) {
    return SETTINGS_AGENTS_LOADOUT_PATH;
  }
  if (skill.required_oauth_issuers && skill.required_oauth_issuers.length > 0 && !skill.available) {
    return SETTINGS_GOOGLE_OAUTH_PATH;
  }
  if (isGoogleWorkspaceOAuthUnavailable(skill)) {
    return SETTINGS_GOOGLE_OAUTH_PATH;
  }
  if (isXLiveSearchUnavailable(skill)) {
    return SETTINGS_PROVIDERS_PATH;
  }
  return SETTINGS_SKILLS_PATH;
}

export function getIntegrationSkillSettingsLinkLabel(skill: Skill, t: SkillsCardTranslator): string {
  if (skill.required_mcp_server_ids && skill.required_mcp_server_ids.length > 0 && !skill.available) {
    return t('card.integrationOAuth.envSkill.configureInSettings');
  }
  if (skill.required_oauth_issuers && skill.required_oauth_issuers.length > 0 && !skill.available) {
    return t('card.integrationOAuth.googleWorkspace.connectInSettings');
  }
  if (isGoogleWorkspaceOAuthUnavailable(skill)) {
    return t('card.integrationOAuth.googleWorkspace.connectInSettings');
  }
  if (isXLiveSearchUnavailable(skill)) {
    return t('card.integrationOAuth.xLiveSearch.connectInSettings');
  }
  return t('card.integrationOAuth.envSkill.configureInSettings');
}

export function getSkillUnavailableDisplayMessage(skill: Skill, t: SkillsCardTranslator): string {
  if (isIntegrationConnectionMissing(skill)) {
    return t('card.integrationOAuth.connectionRequired.unavailable');
  }
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
