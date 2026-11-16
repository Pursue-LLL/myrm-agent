import { describe, expect, it, beforeAll } from 'vitest';

import {
  getClarificationNotificationTitle,
  preloadNotificationCopy,
  resolveStreamLocale,
} from '../streamNotificationCopy';

describe('streamNotificationCopy', () => {
  beforeAll(async () => {
    await preloadNotificationCopy();
  });

  it('resolves supported stream locales', () => {
    expect(resolveStreamLocale('zh-CN')).toBe('zh');
    expect(resolveStreamLocale('zh-TW')).toBe('zh');
    expect(resolveStreamLocale('en-US')).toBe('en');
  });

  it('resolves a language the app does not ship to English', () => {
    expect(resolveStreamLocale('ja')).toBe('en');
    expect(resolveStreamLocale('ko-KR')).toBe('en');
    expect(resolveStreamLocale('de-DE')).toBe('en');
  });

  it('reads clarificationNeeded from locale SSOT for both languages', () => {
    expect(getClarificationNotificationTitle('en')).toBe('Agent needs your input');
    expect(getClarificationNotificationTitle('zh')).toBe('Agent 需要您的输入');
  });

  it('titles a language the app does not ship in English', () => {
    expect(getClarificationNotificationTitle('ja')).toBe('Agent needs your input');
  });
});
