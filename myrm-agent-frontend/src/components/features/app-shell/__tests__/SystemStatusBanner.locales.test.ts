import { describe, expect, it } from 'vitest';
import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zh from '../../../../../locales/zh.json';

const REQUIRED_KEYS = [
  'databaseRecoveredTitle',
  'databaseRecoveredDesc',
  'databaseResetConfirm',
  'databaseResetSuccessTitle',
  'databaseResetSuccessDesc',
  'databaseResetFailedTitle',
  'databaseResetFailedDesc',
  'databaseResetFailedNetwork',
  'databaseDegradedTitle',
  'databaseDegradedBody',
  'databaseResetting',
  'databaseResetNow',
] as const;

type LocaleBundle = Record<string, unknown>;

function notifications(bundle: LocaleBundle): Record<string, string> {
  const notificationsBlock = bundle.notifications;
  if (!notificationsBlock || typeof notificationsBlock !== 'object') {
    throw new Error('notifications namespace missing');
  }
  return notificationsBlock as Record<string, string>;
}

describe('SystemStatusBanner locale keys', () => {
  const bundles = [
    ['en', en],
    ['zh', zh],
    ['de', de],
    ['ko', ko],
    ['ja', ja],
  ] as const;

  it.each(bundles)('%s has all database banner notification keys', (_label, bundle) => {
    const messages = notifications(bundle as LocaleBundle);
    for (const key of REQUIRED_KEYS) {
      expect(messages[key], `${key} missing`).toBeTruthy();
      expect(typeof messages[key]).toBe('string');
    }
  });

  it('english and chinese copies differ from each other', () => {
    const enMessages = notifications(en as LocaleBundle);
    const zhMessages = notifications(zh as LocaleBundle);
    expect(enMessages.databaseDegradedTitle).not.toBe(zhMessages.databaseDegradedTitle);
    expect(enMessages.databaseResetNow).not.toBe(zhMessages.databaseResetNow);
  });
});
