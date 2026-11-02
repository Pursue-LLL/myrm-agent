/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import de from '../../../../../../../locales/de.json';
import en from '../../../../../../../locales/en.json';
import ja from '../../../../../../../locales/ja.json';
import ko from '../../../../../../../locales/ko.json';
import zh from '../../../../../../../locales/zh.json';
import zhTW from '../../../../../../../locales/zh-TW.json';
import { CustomRulesListEditor } from '../CustomRulesListEditor';
import { KNOWN_PERMISSIONS } from '../securityPolicyUtils';

// The label lookup is the behaviour under test, so the real next-intl runs instead of the global mock.
vi.mock('next-intl', async (importOriginal) => await importOriginal());

const LOCALES = { en, zh, 'zh-TW': zhTW, ja, ko, de };

describe.each(Object.entries(LOCALES))('CustomRulesListEditor permission dropdown (%s)', (locale, messages) => {
  it('offers every known permission under its translated name', async () => {
    const onError = vi.fn();
    render(
      <NextIntlClientProvider locale={locale} messages={messages} onError={onError}>
        <CustomRulesListEditor
          rules={[{ permission: '', pattern: '', action: 'ask' }]}
          onAddRule={vi.fn()}
          onRemoveRule={vi.fn()}
          onRuleChange={vi.fn()}
        />
      </NextIntlClientProvider>,
    );

    fireEvent.click(screen.getAllByRole('combobox')[0]);
    const labels = (await screen.findAllByRole('option')).map((option) => option.textContent);

    const names: Record<string, string> = messages.settings.securityPolicy.permissionTypes;
    expect(labels).toEqual(KNOWN_PERMISSIONS.map((permission) => names[permission]));
    expect(onError).not.toHaveBeenCalled();
  });
});
