import { describe, expect, it } from 'vitest';

import { resolveDoctorMessageKey } from '../connectDoctor';

describe('resolveDoctorMessageKey', () => {
  it('maps every known detail code to its dedicated message key', () => {
    expect(resolveDoctorMessageKey('verified', true)).toBe('doctorHealthyVerified');
    expect(resolveDoctorMessageKey('token_valid', true)).toBe('doctorHealthyTokenValid');
    expect(resolveDoctorMessageKey('config_file_missing', false)).toBe('doctorDetailConfigMissing');
    expect(resolveDoctorMessageKey('entry_missing', false)).toBe('doctorDetailEntryMissing');
    expect(resolveDoctorMessageKey('token_mismatch', false)).toBe('doctorDetailTokenMismatch');
    expect(resolveDoctorMessageKey('file_unreadable', false)).toBe('doctorDetailFileUnreadable');
  });

  it('falls back to the generic key for unknown detail codes', () => {
    expect(resolveDoctorMessageKey('unknown', false)).toBe('doctorUnhealthy');
    expect(resolveDoctorMessageKey('unknown', true)).toBe('doctorHealthy');
  });
});
