import { describe, expect, it, vi } from 'vitest';

import type { MCPScanFinding } from '@/store/config/types';
import type { SettingsTranslate } from '../mcpScanFindingText';
import {
  formatMcpFindingWithField,
  formatMcpGateBlockedMessage,
  getMcpFindingDescription,
  getMcpFindingRecommendation,
  parseMcpFindingsFromApiErrorDetails,
} from '@/lib/utils/mcp-config';
import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zhTW from '../../../../../locales/zh-TW.json';
import zh from '../../../../../locales/zh.json';

// The global test setup replaces next-intl. A hand-written stub cannot show how a missing key behaves, so the real
// translator runs over the shipped messages, exactly as the settings components use it.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

// The components see `useTranslations('settings')` with plain string keys; `createTranslator` derives key types from the
// message object, so it is viewed through the same contract the helpers declare.
function settingsTranslator(locale: keyof typeof locales): SettingsTranslate {
  return createTranslator({ locale, messages: locales[locale], namespace: 'settings' }) as unknown as SettingsTranslate;
}

function finding(overrides: Partial<MCPScanFinding> = {}): MCPScanFinding {
  return {
    threatType: 'prompt_injection',
    severity: 'high',
    description: 'English fallback',
    field: 'description',
    recommendation: 'English recommendation',
    ...overrides,
  };
}

/** What the server reports for an env entry such as LD_PRELOAD (harness toolkits/mcp/config_scan.py). */
const ENV_INJECTION = finding({
  threatType: 'dangerous_env_injection',
  severity: 'critical',
  description:
    "Environment variable 'LD_PRELOAD' is a dangerous injection vector: prohibited high-risk system variable",
  field: 'extra_params.env.LD_PRELOAD',
  recommendation: 'Remove this dangerous environment variable to prevent arbitrary code execution',
});

describe('mcpScanFindingText', () => {
  it('maps threatType to the localized description and recommendation', () => {
    const t = settingsTranslator('zh');

    expect(getMcpFindingDescription(finding(), t)).toBe(zh.settings.mcpThreat.prompt_injection);
    expect(getMcpFindingRecommendation(finding(), t)).toBe(zh.settings.mcpThreatRec.prompt_injection);
  });

  it('shows the server text, not a key path, when a threat type has no translation yet', () => {
    const t = settingsTranslator('de');
    const unknown = finding({ threatType: 'threat_type_added_by_a_newer_server' });

    expect(getMcpFindingDescription(unknown, t)).toBe('English fallback');
    expect(getMcpFindingRecommendation(unknown, t)).toBe('English recommendation');
  });

  it('has no recommendation when the server sent none', () => {
    expect(
      getMcpFindingRecommendation(finding({ recommendation: undefined }), settingsTranslator('en')),
    ).toBeUndefined();
  });

  it.each(Object.keys(locales) as Array<keyof typeof locales>)(
    '%s: a dangerous environment variable is described in the locale, with the variable still visible in the field',
    (locale) => {
      const t = settingsTranslator(locale);
      const { mcpThreat, mcpThreatRec } = locales[locale].settings;

      expect(getMcpFindingDescription(ENV_INJECTION, t)).toBe(mcpThreat.dangerous_env_injection);
      expect(getMcpFindingRecommendation(ENV_INJECTION, t)).toBe(mcpThreatRec.dangerous_env_injection);
      expect(getMcpFindingDescription(ENV_INJECTION, t)).not.toContain('Environment variable');
      expect(formatMcpFindingWithField(ENV_INJECTION, t)).toContain('extra_params.env.LD_PRELOAD');
    },
  );

  it.each(Object.keys(locales) as Array<keyof typeof locales>)(
    '%s: every threat type has both a description and a recommendation',
    (locale) => {
      const { mcpThreat, mcpThreatRec } = locales[locale].settings;

      expect(Object.keys(mcpThreatRec).sort()).toEqual(Object.keys(mcpThreat).sort());
      expect(Object.keys(mcpThreat)).toContain('dangerous_env_injection');
    },
  );

  it('parses structured findings from API error details', () => {
    const payload = JSON.stringify({
      threatType: 'name_injection',
      severity: 'high',
      description: 'Tool name contains injection-like content',
      recommendation: 'Rename the tool',
    });
    const findings = parseMcpFindingsFromApiErrorDetails([{ field: 'tool.name', issue: payload }]);
    expect(findings).toHaveLength(1);
    expect(findings[0]?.threatType).toBe('name_injection');
  });

  it('prefers verify findings in gate blocked message', () => {
    const message = formatMcpGateBlockedMessage(
      {
        verifyError: 'raw english error',
        verifyFindings: [finding({ threatType: 'name_injection', field: 'tool.name' })],
        fallback: 'fallback',
      },
      settingsTranslator('zh'),
    );
    expect(message).toContain(zh.settings.mcpThreat.name_injection);
    expect(message).toContain('tool.name');
  });

  it('blocks a dangerous environment variable with the localized reason and the variable name', () => {
    const message = formatMcpGateBlockedMessage(
      { staticFindings: [ENV_INJECTION], fallback: 'fallback' },
      settingsTranslator('de'),
    );

    expect(message).toBe(`${de.settings.mcpThreat.dangerous_env_injection} (extra_params.env.LD_PRELOAD)`);
  });
});
