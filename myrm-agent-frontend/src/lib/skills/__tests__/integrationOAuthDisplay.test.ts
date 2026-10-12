/**
 * Tests for multi-connector declarative preflight and integrationOAuthDisplay generic paths.
 */

import { describe, it, expect } from 'vitest';
import {
  hasIntegrationSettingsLink,
  getIntegrationSkillSettingsPath,
  getIntegrationSkillSettingsLinkLabel,
  getSkillUnavailableDisplayMessage,
  isEnvGatedSkillUnavailable,
  SETTINGS_GOOGLE_OAUTH_PATH,
  SETTINGS_AGENTS_LOADOUT_PATH,
  SETTINGS_SKILLS_PATH,
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
    is_active: true,
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
    traps: [],
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
      is_active: true,
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
      traps: [],
      verification_steps: [],
      eval_cases: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(hasIntegrationSettingsLink(skill)).toBe(true);
    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_GOOGLE_OAUTH_PATH);
    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toContain('google_workspace');
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
      is_active: true,
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
      traps: [],
      verification_steps: [],
      eval_cases: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(hasIntegrationSettingsLink(skill)).toBe(true);
    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_AGENTS_LOADOUT_PATH);
  });
});

describe('integrationOAuthDisplay env-gated skills', () => {
  const mockTranslator = (key: string) => key;

  const unavailable = (requires: SkillRequires, id = 'imap-smtp-email'): Skill =>
    buildSkill({ id, available: false, unavailable_reason: 'Missing: ENV: X', requires });

  it('treats any skill that only requires env keys as configurable in settings', () => {
    const skill = unavailable({ bins: [], env: ['EMAIL_IMAP_HOST', 'EMAIL_IMAP_USER'], config: [] });

    expect(isEnvGatedSkillUnavailable(skill)).toBe(true);
    expect(hasIntegrationSettingsLink(skill)).toBe(true);
    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_SKILLS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(
      'card.integrationOAuth.envSkill.configureInSettings',
    );
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
