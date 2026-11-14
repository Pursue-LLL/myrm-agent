/**
 * Which settings page and wording an unavailable skill gets, by the requirements the skills API says it declares.
 */

import { describe, it, expect } from 'vitest';
import {
  hasIntegrationSettingsLink,
  getIntegrationSkillSettingsPath,
  getIntegrationSkillSettingsLinkLabel,
  getSkillUnavailableDisplayMessage,
  isXurlBinUnavailable,
  GOOGLE_WORKSPACE_SKILL_ID,
  SETTINGS_CREDENTIALS_PATH,
  SETTINGS_AGENTS_LOADOUT_PATH,
  SETTINGS_SKILLS_PATH,
  X_LIVE_SEARCH_SKILL_ID,
} from '../integrationOAuthDisplay';
import type { Skill } from '@/store/skill/types';
import { buildSkill } from './integrationOAuthDisplayFixtures';

describe('integrationOAuthDisplay settings link by what the skill declares', () => {
  const mockTranslator = (key: string) => key;
  const CONFIGURE = 'card.integrationOAuth.envSkill.configureInSettings';
  const CONNECT = 'card.integrationOAuth.googleWorkspace.connectInSettings';
  const unavailable = (overrides: Partial<Skill>): Skill =>
    buildSkill({ available: false, unavailable_reason: 'raw reason', ...overrides });

  it.each([
    ['a connector', { required_mcp_server_ids: ['notion'] }, true],
    ['an account', { required_oauth_issuers: ['github'] }, true],
    ['Google Workspace with no declared account', { id: GOOGLE_WORKSPACE_SKILL_ID }, true],
    ['X live search with no declared account', { id: X_LIVE_SEARCH_SKILL_ID }, true],
    ['only env keys', { requires: { bins: [], env: ['API_KEY'], config: [] } }, false],
    ['nothing it can name', {}, false],
  ] satisfies [string, Partial<Skill>, boolean][])(
    'a skill waiting on %s: settings link is %s',
    (_, declared, linked) => {
      expect(hasIntegrationSettingsLink(unavailable(declared))).toBe(linked);
    },
  );

  it('sends a skill that declares nothing to the skills page with the configure wording', () => {
    const skill = unavailable({});

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_SKILLS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(CONFIGURE);
  });

  it('treats a payload that omits both lists like one whose lists are empty', () => {
    const skill = unavailable({ required_oauth_issuers: undefined, required_mcp_server_ids: undefined });

    expect(hasIntegrationSettingsLink(skill)).toBe(false);
    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_SKILLS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(CONFIGURE);
  });

  it('puts a connector ahead of an account when a skill declares both', () => {
    const skill = unavailable({ required_mcp_server_ids: ['notion'], required_oauth_issuers: ['github'] });

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_AGENTS_LOADOUT_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(CONFIGURE);
  });

  it('words an account as connecting it even when the connector list is empty', () => {
    const skill = unavailable({ required_oauth_issuers: ['github'], required_mcp_server_ids: [] });

    expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_CREDENTIALS_PATH);
    expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(CONNECT);
  });

  it.each([
    ['a connector', { required_mcp_server_ids: ['notion'] }],
    ['an account', { required_oauth_issuers: ['github'] }],
    ['Google Workspace', { id: GOOGLE_WORKSPACE_SKILL_ID }],
    ['X live search', { id: X_LIVE_SEARCH_SKILL_ID }],
  ] satisfies [string, Partial<Skill>][])(
    'a skill that waited on %s sends nobody anywhere once it is available',
    (_, declared) => {
      const skill = buildSkill({ ...declared, available: true });

      expect(hasIntegrationSettingsLink(skill)).toBe(false);
      expect(getIntegrationSkillSettingsPath(skill)).toBe(SETTINGS_SKILLS_PATH);
      expect(getIntegrationSkillSettingsLinkLabel(skill, mockTranslator)).toBe(CONFIGURE);
    },
  );

  it('flags the xurl CLI only while xurl is unavailable', () => {
    expect(isXurlBinUnavailable(unavailable({ id: 'xurl' }))).toBe(true);
    expect(isXurlBinUnavailable(buildSkill({ id: 'xurl', available: true }))).toBe(false);
    expect(isXurlBinUnavailable(unavailable({ id: 'imap-smtp-email' }))).toBe(false);
  });

  it('gives an available xurl skill no xurl-specific message', () => {
    const skill = buildSkill({ id: 'xurl', available: true, unavailable_reason: null });

    expect(getSkillUnavailableDisplayMessage(skill, mockTranslator)).toBe('card.unavailable');
  });
});
