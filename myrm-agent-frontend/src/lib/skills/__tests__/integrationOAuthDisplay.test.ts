/**
 * Tests for multi-connector declarative preflight and integrationOAuthDisplay generic paths.
 */

import { describe, it, expect } from 'vitest';
import {
  hasIntegrationSettingsLink,
  getIntegrationSkillSettingsPath,
  getIntegrationSkillSettingsLinkLabel,
  formatOAuthIssuerLabel,
  getSkillUnavailableDisplayMessage,
  isEnvGatedSkillUnavailable,
  SETTINGS_CREDENTIALS_PATH,
  SETTINGS_PROVIDERS_PATH,
  SETTINGS_AGENTS_LOADOUT_PATH,
  SETTINGS_SKILLS_PATH,
  X_LIVE_SEARCH_SKILL_ID,
} from '../integrationOAuthDisplay';
import type { Skill, SkillRequires } from '@/store/skill/types';

function buildSkill(overrides: Partial<Skill>): Skill {
  return {
    id: 'custom-skill',
    name: 'Custom Skill',
    description: 'test',
    type: 'prebuilt',
    storage_path: '/skills/custom',
    version: '1.0.0',
    category: 'office',
    icon_url: null,
    tags: [],
    requires: { bins: [], env: [], config: [] },
    available: true,
    unavailable_reason: null,
    trust: 'installed',
    author: null,
    homepage: null,
    always: false,
    model_invocable: true,
    user_invocable: true,
    primary_env: null,
    security: null,
    user_trusted: false,
    evolution_locked: false,
    has_upstream_update: false,
    verification_steps: [],
    eval_cases: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('integrationOAuthDisplay generic multi-connector paths', () => {
  const mockTranslator = (key: string) => key;

  it('detects missing connectors from declarative required_oauth_issuers', () => {
    const skill: Skill = {
      id: 'custom-meeting-sync',
      name: 'Meeting Sync',
      description: 'Syncs notes',
      type: 'prebuilt',
      storage_path: '/skills/meeting',
      version: '1.0.0',
      category: 'office',
      icon_url: null,
      tags: [],
      requires: { bins: [], env: [], config: [] },
      available: false,
      unavailable_reason: 'Connect google_workspace in Settings → Integrations → Credentials',
      required_oauth_issuers: ['google_workspace'],
      trust: 'installed',
      author: null,
      homepage: null,
      always: false,
      model_invocable: true,
      user_invocable: true,
      primary_env: null,
      security: null,
      user_trusted: false,
      evolution_locked: false,
      has_upstream_update: false,
      verification_steps: [],
      eval_cases: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(hasIntegrationSettingsLink(skill)).toBe(true);
    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_CREDENTIALS_PATH);
    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe(
      'card.integrationOAuth.connectionRequired.unavailable',
    );
  });

  it('routes to agents loadout when required_mcp_server_ids is missing', () => {
    const skill: Skill = {
      id: 'custom-db-inspector',
      name: 'DB Inspector',
      description: 'Inspects DB',
      type: 'prebuilt',
      storage_path: '/skills/db',
      version: '1.0.0',
      category: 'operations',
      icon_url: null,
      tags: [],
      requires: { bins: [], env: [], config: [] },
      available: false,
      unavailable_reason: 'Requires MCP server: postgres-mcp',
      required_mcp_server_ids: ['postgres-mcp'],
      trust: 'installed',
      author: null,
      homepage: null,
      always: false,
      model_invocable: true,
      user_invocable: true,
      primary_env: null,
      security: null,
      user_trusted: false,
      evolution_locked: false,
      has_upstream_update: false,
      verification_steps: [],
      eval_cases: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(hasIntegrationSettingsLink(skill)).toBe(true);
    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_AGENTS_LOADOUT_PATH);
    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe(
      'card.integrationOAuth.connectionRequired.unavailable',
    );
  });

  it('never shows the server-provided English reason for a missing account or connector', () => {
    const skill = buildSkill({
      available: false,
      unavailable_reason: 'Connect google_workspace in Settings → Integrations → Credentials',
      required_oauth_issuers: ['google_workspace'],
      required_mcp_server_ids: ['notion'],
    });

    expect(getSkillUnavailableDisplayMessage(skill, (key: string) => `translated:${key}`)).toBe(
      'translated:card.integrationOAuth.connectionRequired.unavailable',
    );
  });

  it('shows the server reason when a bin, env or config requirement can also be what blocks the skill', () => {
    const missingBin = buildSkill({
      available: false,
      unavailable_reason: 'Missing: BIN: gh',
      requires: { bins: ['gh'], env: [], config: [] },
      required_oauth_issuers: ['github'],
    });
    const missingKey = buildSkill({
      available: false,
      unavailable_reason: 'Missing: ENV: GH_TOKEN',
      requires: { bins: [], env: ['GH_TOKEN'], config: [] },
      required_mcp_server_ids: ['github'],
    });

    expect(getSkillUnavailableDisplayMessage(missingBin, mockTranslator)).toBe('Missing: BIN: gh');
    expect(getSkillUnavailableDisplayMessage(missingKey, mockTranslator)).toBe('Missing: ENV: GH_TOKEN');
    expect(hasIntegrationSettingsLink(missingBin)).toBe(true);
    expect(hasIntegrationSettingsLink(missingKey)).toBe(true);
  });

  it('keeps the dedicated Google Workspace message when the skill declares no required accounts', () => {
    const skill = buildSkill({ id: 'google-workspace', available: false, unavailable_reason: 'raw reason' });

    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe(
      'card.integrationOAuth.googleWorkspace.unavailable',
    );
  });
});

describe('formatOAuthIssuerLabel', () => {
  it('turns issuer ids into capitalised words', () => {
    expect(formatOAuthIssuerLabel('google_workspace')).toBe('Google Workspace');
    expect(formatOAuthIssuerLabel('x-live-search')).toBe('X Live Search');
  });

  it('keeps already-cased ids and ignores empty segments', () => {
    expect(formatOAuthIssuerLabel('OAuth')).toBe('OAuth');
    expect(formatOAuthIssuerLabel('__github__')).toBe('Github');
  });

  it('spells brand names the way the brand does', () => {
    expect(formatOAuthIssuerLabel('xai')).toBe('xAI');
  });

  it('never resolves an id to an inherited object property', () => {
    expect(formatOAuthIssuerLabel('constructor')).toBe('Constructor');
    expect(formatOAuthIssuerLabel('toString')).toBe('ToString');
  });
});

describe('getIntegrationSkillSettingsPath account routing', () => {
  it.each(['google_workspace', 'xai', 'github'])(
    'sends a skill waiting on the %s account to the Credentials page',
    (issuer) => {
      const skill = buildSkill({
        available: false,
        unavailable_reason: 'Missing account',
        required_oauth_issuers: [issuer],
      });

      expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_CREDENTIALS_PATH);
    },
  );

  it('sends the X live search skill to the Models page when it declares no account', () => {
    const skill = buildSkill({ id: 'x-live-search', available: false, unavailable_reason: 'raw reason' });

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_PROVIDERS_PATH);
  });
});

describe('integrationOAuthDisplay settings link of every other skill', () => {
  const mockTranslator = (key: string) => key;

  it('sends a skill waiting on a connector to the agents loadout and words it as configuration', () => {
    const skill = buildSkill({ available: false, required_mcp_server_ids: ['notion'] });

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_AGENTS_LOADOUT_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(
      'card.integrationOAuth.envSkill.configureInSettings',
    );
  });

  it('sends a skill waiting on a declared account to Credentials and words it as connecting the account', () => {
    const skill = buildSkill({ available: false, required_oauth_issuers: ['github'] });

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_CREDENTIALS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(
      'card.integrationOAuth.googleWorkspace.connectInSettings',
    );
  });

  it('keeps Google Workspace on Credentials when the catalog declares no account for it', () => {
    const skill = buildSkill({ id: 'google-workspace', available: false });

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_CREDENTIALS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(
      'card.integrationOAuth.googleWorkspace.connectInSettings',
    );
  });

  it('falls back to the skills page for a skill that waits on nothing it can name', () => {
    const skill = buildSkill({ available: false });

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_SKILLS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(
      'card.integrationOAuth.envSkill.configureInSettings',
    );
  });
});

describe('integrationOAuthDisplay when the server gave no reason', () => {
  const mockTranslator = (key: string) => key;

  it('shows the generic unavailable text for a skill that also waits on a bin, env or config', () => {
    const skill = buildSkill({
      available: false,
      unavailable_reason: null,
      requires: { bins: ['gh'], env: [], config: [] },
      required_oauth_issuers: ['github'],
    });

    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe('card.unavailable');
  });

  it('shows the generic unavailable text for a skill that names nothing it waits on', () => {
    const skill = buildSkill({ available: false, unavailable_reason: null });

    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe('card.unavailable');
  });
});

describe('integrationOAuthDisplay X live search as the catalog lists it', () => {
  const mockTranslator = (key: string) => key;

  // The catalog entry declares its xAI account through the SKILL.md frontmatter, like any account-bound skill.
  const xLiveSearch = buildSkill({
    id: X_LIVE_SEARCH_SKILL_ID,
    available: false,
    unavailable_reason:
      'Add an xAI provider in Settings → Models & Providers, or connect your SuperGrok token in Settings → Integrations → Credentials',
    required_oauth_issuers: ['xai'],
  });

  it('guides to the provider settings rather than the generic account prompt', () => {
    expect(hasIntegrationSettingsLink(xLiveSearch)).toBe(true);
    expect(getIntegrationSkillSettingsPath(xLiveSearch)).toBe(SETTINGS_PROVIDERS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(xLiveSearch, mockTranslator)).toBe(
      'card.integrationOAuth.xLiveSearch.connectInSettings',
    );
    expect(getSkillUnavailableDisplayMessage(xLiveSearch, mockTranslator)).toBe(
      'card.integrationOAuth.xLiveSearch.unavailable',
    );
  });

  it('offers no settings link once the skill is available', () => {
    expect(hasIntegrationSettingsLink({ ...xLiveSearch, available: true, unavailable_reason: null })).toBe(false);
  });
});

describe('integrationOAuthDisplay env-gated skills', () => {
  const mockTranslator = (key: string) => key;

  const unavailable = (requires: SkillRequires, id = 'imap-smtp-email'): Skill =>
    buildSkill({ id, available: false, unavailable_reason: 'Missing: ENV: X', requires });

  it('treats any skill that only requires env keys as an in-place key action, not a settings link', () => {
    const skill = unavailable({ bins: [], env: ['EMAIL_IMAP_HOST', 'EMAIL_IMAP_USER'], config: [] });

    expect(isEnvGatedSkillUnavailable(skill)).toBe(true);
    expect(hasIntegrationSettingsLink(skill)).toBe(false);
    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe('card.integrationOAuth.envSkill.unavailable');
  });

  it('does not flag an available skill', () => {
    const skill = buildSkill({ requires: { bins: [], env: ['NOTION_API_KEY'], config: [] }, available: true });

    expect(isEnvGatedSkillUnavailable(skill)).toBe(false);
    expect(hasIntegrationSettingsLink(skill)).toBe(false);
  });

  it('does not offer the key CTA when bins or config are also required', () => {
    const withBins = unavailable({ bins: ['gh'], env: ['GH_TOKEN'], config: [] });
    const withConfig = unavailable({ bins: [], env: ['API_KEY'], config: ['~/.cfg'] });

    expect(isEnvGatedSkillUnavailable(withBins)).toBe(false);
    expect(isEnvGatedSkillUnavailable(withConfig)).toBe(false);
    expect(hasIntegrationSettingsLink(withBins)).toBe(false);
    expect(getSkillUnavailableDisplayMessage(withBins, mockTranslator)).toBe('Missing: ENV: X');
  });

  it('does not flag skills without env requirements', () => {
    expect(isEnvGatedSkillUnavailable(unavailable({ bins: ['xurl'], env: [], config: [] }, 'xurl'))).toBe(false);
    expect(isEnvGatedSkillUnavailable(unavailable({ bins: [], env: [], config: [] }))).toBe(false);
  });

  it('keeps the xurl-specific message for the missing CLI', () => {
    const skill = unavailable({ bins: ['xurl'], env: [], config: [] }, 'xurl');

    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe('card.integrationOAuth.xurl.unavailable');
  });
});
