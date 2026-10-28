/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import de from '../../../../../../locales/de.json';
import en from '../../../../../../locales/en.json';
import ja from '../../../../../../locales/ja.json';
import ko from '../../../../../../locales/ko.json';
import zhTW from '../../../../../../locales/zh-TW.json';
import zh from '../../../../../../locales/zh.json';
import { BROWSER_SESSION_ACTIONS } from '@/lib/approval/browserSession';

import BrowserSessionView from '../BrowserSessionView';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

const LOCALES = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

// What a person reading the card must not have to understand: algorithm names, storage paths, browser storage APIs.
const TECHNICAL_DETAIL = /AES|GCM|~\/|\.myrm|cookie|localstorage/i;

function renderIn(locale: keyof typeof LOCALES, action: (typeof BROWSER_SESSION_ACTIONS)[number], domain = '') {
  return render(
    <NextIntlClientProvider locale={locale} messages={LOCALES[locale]}>
      <BrowserSessionView action={action} domain={domain} />
    </NextIntlClientProvider>,
  );
}

describe('BrowserSessionView', () => {
  it('shows the action and the site in the language of the interface', () => {
    renderIn('en', 'save_session', 'example.com');

    expect(screen.getByText('Save Login State')).toBeTruthy();
    expect(screen.getByText('example.com')).toBeTruthy();
  });

  it('names "all domains" when the action is not about one site', () => {
    renderIn('de', 'list_sessions');

    expect(screen.getByText('Alle Domänen')).toBeTruthy();
    expect(screen.getByText('Gespeicherte Sitzungen anzeigen')).toBeTruthy();
  });

  describe.each(Object.keys(LOCALES) as (keyof typeof LOCALES)[])('in %s', (locale) => {
    it.each(BROWSER_SESSION_ACTIONS)('explains %s without technical detail', (action) => {
      const { container } = renderIn(locale, action, 'example.com');

      const text = container.textContent ?? '';
      expect(text).not.toMatch(TECHNICAL_DETAIL);
      expect(text).not.toContain('browserSession.');
      expect(text).toContain(LOCALES[locale].toolApproval.browserSession.actions[action].label);
      expect(text).toContain(LOCALES[locale].toolApproval.browserSession.actions[action].desc);
    });
  });
});
