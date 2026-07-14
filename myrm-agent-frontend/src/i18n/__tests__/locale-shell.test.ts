import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  DEFERRED_SETTINGS_SECTIONS,
  SSR_SHELL_SETTINGS_SECTIONS,
} from '@/i18n/locale-manifest';
import { mergeMessages } from '@/i18n/merge-messages';

const localesRoot = join(process.cwd(), 'locales/namespaces');

function readSettingsSection(locale: string, section: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(localesRoot, locale, 'settings', `${section}.json`), 'utf-8')) as Record<
    string,
    unknown
  >;
}

describe('locale shell settings', () => {
  it('includes chat-critical defaultModel keys in SSR shell sections', () => {
    expect(SSR_SHELL_SETTINGS_SECTIONS).toContain('defaultModel');
    expect(SSR_SHELL_SETTINGS_SECTIONS).toContain('modelCapabilities');

    const required = ['primaryModel', 'fallbackSlot', 'notSet', 'searchModels', 'noEnabledModels', 'noMatchingModels'];
    for (const locale of ['zh', 'en'] as const) {
      const defaultModel = readSettingsSection(locale, 'defaultModel');
      for (const key of required) {
        expect(defaultModel[key], `${locale}.defaultModel.${key}`).toBeTruthy();
      }

      const modelCapabilities = readSettingsSection(locale, 'modelCapabilities');
      expect(modelCapabilities.contextWindow, `${locale}.modelCapabilities.contextWindow`).toBeTruthy();
      expect(modelCapabilities.refCost, `${locale}.modelCapabilities.refCost`).toBeTruthy();
    }
  });

  it('keeps shell settings out of deferred sections', () => {
    for (const section of SSR_SHELL_SETTINGS_SECTIONS) {
      expect(DEFERRED_SETTINGS_SECTIONS).not.toContain(section);
    }
  });

  it('merges deferred settings alongside shell settings', () => {
    const shell = {
      chat: { title: 'Chat' },
      settings: {
        menu: { defaultModel: 'Default Model' },
        defaultModel: { searchModels: 'Search models...' },
      },
    } as const;

    const deferred = {
      settings: {
        account: { title: 'Account' },
      },
    };

    const merged = mergeMessages(shell, deferred);
    expect(merged.settings.defaultModel?.searchModels).toBe('Search models...');
    expect(merged.settings.account?.title).toBe('Account');
  });
});
