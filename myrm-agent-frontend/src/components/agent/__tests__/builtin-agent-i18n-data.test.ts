import { describe, expect, it } from 'vitest';

import { BUILTIN_AGENT_I18N } from '../builtin-agent-i18n-data';

const REQUIRED_LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'] as const;

describe('BUILTIN_AGENT_I18N', () => {
  it('should define non-empty name and description for every locale on each builtin agent', () => {
    for (const [agentId, entry] of Object.entries(BUILTIN_AGENT_I18N)) {
      for (const locale of REQUIRED_LOCALES) {
        const strings = entry[locale];
        expect(strings?.name, `${agentId}.${locale}.name`).toBeTruthy();
        expect(strings?.description, `${agentId}.${locale}.description`).toBeTruthy();
      }
    }
  });

  it('should expose Knowledge Work preset for builtin-economy in English', () => {
    const economy = BUILTIN_AGENT_I18N['builtin-economy'];
    expect(economy).toBeDefined();
    expect(economy.en.name).toBe('Knowledge Work');
    expect(economy.en.description).toContain('Deliverable-first');
  });

  it('should expose Chinese Knowledge Work name for builtin-economy', () => {
    const economy = BUILTIN_AGENT_I18N['builtin-economy'];
    expect(economy.zh.name).toBe('知识工作助手');
    expect(economy['zh-TW'].name).toBe('知識工作助手');
  });
});
