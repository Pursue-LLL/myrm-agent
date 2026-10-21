import { describe, expect, it, vi } from 'vitest';

import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zhTW from '../../../../../locales/zh-TW.json';
import zh from '../../../../../locales/zh.json';

// The global test setup replaces next-intl, so the real formatter is loaded explicitly.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

const EVIDENCE_KEYS = [
  'drawerTitle',
  'quoteMatch',
  'toolExecution',
  'toolFailed',
  'copyToolOutput',
  'roleAssistant',
  'roleUser',
  'loadFailed',
] as const;

describe('evidence drawer messages', () => {
  it.each(Object.keys(locales) as (keyof typeof locales)[])('%s formats every evidence key', (locale) => {
    const t = createTranslator({ locale, messages: locales[locale], namespace: 'memory.commandCenter.evidence' });

    for (const key of EVIDENCE_KEYS) {
      const message = t(key, { quote: 'pnpm' });
      expect(message, `${locale}:${key}`).not.toBe(`memory.commandCenter.evidence.${key}`);
      expect(message.length).toBeGreaterThan(0);
    }
    expect(t('quoteMatch', { quote: 'pnpm' })).toContain('pnpm');
  });
});
