/**
 * Tests for multi-connector declarative preflight and integrationOAuthDisplay generic paths.
 */

import { describe, it, expect } from 'vitest';
import {
  hasIntegrationSettingsLink,
  getIntegrationSkillSettingsPath,
  getIntegrationSkillSettingsLinkLabel,
  getSkillUnavailableDisplayMessage,
  SETTINGS_GOOGLE_OAUTH_PATH,
  SETTINGS_AGENTS_LOADOUT_PATH,
} from '../integrationOAuthDisplay';
import type { Skill } from '@/store/skill/types';

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
    };

    expect(hasIntegrationSettingsLink(skill)).toBe(true);
    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_AGENTS_LOADOUT_PATH);
  });
});
