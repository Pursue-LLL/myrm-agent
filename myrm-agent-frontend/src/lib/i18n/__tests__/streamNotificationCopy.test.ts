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
    expect(resolveStreamLocale('ja')).toBe('ja');
    expect(resolveStreamLocale('ko-KR')).toBe('ko');
    expect(resolveStreamLocale('de-DE')).toBe('de');
    expect(resolveStreamLocale('en-US')).toBe('en');
  });

  it('reads clarificationNeeded from locale SSOT for all five languages', () => {
    expect(getClarificationNotificationTitle('en')).toBe('Agent needs your input');
    expect(getClarificationNotificationTitle('zh')).toBe('Agent 需要您的输入');
    expect(getClarificationNotificationTitle('ja')).toBe('Agentがあなたの入力を必要としています');
    expect(getClarificationNotificationTitle('ko')).toBe('Agent가 입력을 기다리고 있습니다');
    expect(getClarificationNotificationTitle('de')).toBe('Agent benötigt Ihre Eingabe');
  });
});
