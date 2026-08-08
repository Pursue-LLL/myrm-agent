import { describe, it, expect } from 'vitest';
import {
  isFormalKoreanRepliesEnabled,
  setFormalKoreanRepliesEnabled,
} from '../responseLocalePolicy';

describe('responseLocalePolicy', () => {
  it('returns false when policy is missing', () => {
    expect(isFormalKoreanRepliesEnabled(null)).toBe(false);
    expect(isFormalKoreanRepliesEnabled({})).toBe(false);
  });

  it('detects formal Korean policy', () => {
    expect(
      isFormalKoreanRepliesEnabled({
        response_locale_policy: { locale: 'ko-KR', formality: 'formal-polite' },
      }),
    ).toBe(true);
  });

  it('ignores casual Korean policy', () => {
    expect(
      isFormalKoreanRepliesEnabled({
        response_locale_policy: { locale: 'ko-KR', formality: 'casual' },
      }),
    ).toBe(false);
  });

  it('enables and disables formal Korean policy on engine_params', () => {
    const enabled = setFormalKoreanRepliesEnabled(null, true);
    expect(enabled).toEqual({
      response_locale_policy: { locale: 'ko-KR', formality: 'formal-polite' },
    });

    expect(setFormalKoreanRepliesEnabled(enabled, false)).toBeNull();
  });
});
