import { describe, expect, it, vi } from 'vitest';

import {
  ARCHIVE_SECURITY_I18N_KEYS,
  resolveApiErrorDetail,
  resolveArchiveSecurityErrorI18nKey,
  resolveUserFacingArchiveSecurityError,
} from '../archiveSecurityErrorCore';

describe('archiveSecurityErrorCore', () => {
  it('normalizes structured detail with error_code', () => {
    expect(
      resolveApiErrorDetail(
        {
          message: 'Upload blocked.',
          error_code: 'archive_security.entry_limit_exceeded',
        },
        'Fallback message',
      ),
    ).toEqual({
      message: 'Upload blocked.',
      errorCode: 'archive_security.entry_limit_exceeded',
    });
  });

  it('falls back to detail string when message is missing', () => {
    expect(
      resolveApiErrorDetail(
        {
          detail: 'Legacy detail message',
        },
        'Fallback message',
      ),
    ).toEqual({
      message: 'Legacy detail message',
      errorCode: '',
    });
  });

  it('returns fallback message for unsupported payload shape', () => {
    expect(resolveApiErrorDetail(123, 'Fallback message')).toEqual({
      message: 'Fallback message',
      errorCode: '',
    });
  });

  it('resolves archive_security i18n key only for known codes', () => {
    expect(resolveArchiveSecurityErrorI18nKey('archive_security.total_size_exceeded')).toBe(
      ARCHIVE_SECURITY_I18N_KEYS['archive_security.total_size_exceeded'],
    );
    expect(resolveArchiveSecurityErrorI18nKey('unknown.error.code')).toBeUndefined();
  });

  it('uses translated message when error code is recognized', () => {
    const translate = vi.fn((key: string) => `translated:${key}`);
    expect(
      resolveUserFacingArchiveSecurityError(
        {
          message: 'Raw message',
          error_code: 'archive_security.executable_binary_detected',
        },
        'Fallback message',
        translate,
      ),
    ).toBe(
      `translated:${ARCHIVE_SECURITY_I18N_KEYS['archive_security.executable_binary_detected']}`,
    );
    expect(translate).toHaveBeenCalledTimes(1);
  });

  it('keeps backend message when error code is unknown', () => {
    expect(
      resolveUserFacingArchiveSecurityError(
        {
          message: 'Backend says no',
          error_code: 'other.error.code',
        },
        'Fallback message',
        () => 'should-not-be-used',
      ),
    ).toBe('Backend says no');
  });

  it('falls back to backend message when translation key is missing', () => {
    expect(
      resolveUserFacingArchiveSecurityError(
        {
          message: 'Backend fallback message',
          error_code: 'archive_security.entry_limit_exceeded',
        },
        'Fallback message',
        (key) => key,
      ),
    ).toBe('Backend fallback message');
  });
});
