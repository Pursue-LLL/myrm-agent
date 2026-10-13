import type { Skill } from '@/store/skill/types';

export const GOOGLE_WORKSPACE_SKILL_ID = 'google-workspace';
export const X_LIVE_SEARCH_SKILL_ID = 'x-live-search';
export const XURL_SKILL_ID = 'xurl';

export const SETTINGS_CREDENTIALS_PATH = '/settings/credentials';
export const SETTINGS_PROVIDERS_PATH = '/settings/models';
export const SETTINGS_DEFAULT_MODEL_PATH = '/settings/defaultModel';
export const SETTINGS_AGENTS_LOADOUT_PATH = '/settings/agents#loadout';
export const SETTINGS_SKILLS_PATH = '/settings/skills';

/** LLM-provider OAuth issuers (`provider_openai`, `provider_anthropic`, ...) are connected on the Models page. */
const PROVIDER_OAUTH_ISSUER_PREFIX = 'provider_';

/** Settings page that owns the OAuth connection behind an issuer id. */
export function getOAuthIssuerSettingsPath(issuer: string): string {
  return issuer.startsWith(PROVIDER_OAUTH_ISSUER_PREFIX) ? SETTINGS_PROVIDERS_PATH : SETTINGS_CREDENTIALS_PATH;
}

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

/** An unavailable skill that declares an account or connector it depends on, which is connected in settings. */
function isWaitingOnConnection(skill: Skill): boolean {
  const hasRequiredAccounts = (skill.required_oauth_issuers?.length ?? 0) > 0;
  const hasRequiredConnectors = (skill.required_mcp_server_ids?.length ?? 0) > 0;
  return !skill.available && (hasRequiredAccounts || hasRequiredConnectors);
}

function declaresRuntimeRequirement(skill: Skill): boolean {
  const { bins, env, config } = skill.requires;
  return bins.length + env.length + config.length > 0;
}

export function hasIntegrationSettingsLink(skill: Skill): boolean {
  return isWaitingOnConnection(skill) || isGoogleWorkspaceOAuthUnavailable(skill) || isXLiveSearchUnavailable(skill);
}

export function getIntegrationSkillSettingsPath(skill: Skill): string {
  if (skill.required_mcp_server_ids && skill.required_mcp_server_ids.length > 0 && !skill.available) {
    return SETTINGS_AGENTS_LOADOUT_PATH;
  }
  if (skill.required_oauth_issuers && skill.required_oauth_issuers.length > 0 && !skill.available) {
    return getOAuthIssuerSettingsPath(skill.required_oauth_issuers[0]);
  }
  if (isGoogleWorkspaceOAuthUnavailable(skill)) {
    return SETTINGS_CREDENTIALS_PATH;
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
  if (isWaitingOnConnection(skill)) {
    // The fixed instruction is only true when a connection is the sole possible blocker; otherwise the
    // server reason names the actual cause.
    return declaresRuntimeRequirement(skill)
      ? skill.unavailable_reason || t('card.unavailable')
      : t('card.integrationOAuth.connectionRequired.unavailable');
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
