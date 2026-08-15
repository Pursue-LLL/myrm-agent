import { describe, expect, it } from 'vitest';

import {
  resolveDoctorMessageKey,
  resolveDoctorSeverity,
  resolveDoctorStatusKey,
} from '../connectDoctor';

describe('resolveDoctorMessageKey', () => {
  it('maps every known detail code to its dedicated message key', () => {
    expect(resolveDoctorMessageKey('verified', true)).toBe('doctorHealthyVerified');
    expect(resolveDoctorMessageKey('token_valid', true)).toBe('doctorHealthyTokenValid');
    expect(resolveDoctorMessageKey('token_env', false)).toBe('doctorDetailTokenEnv');
    expect(resolveDoctorMessageKey('token_missing', false)).toBe('doctorDetailTokenMissing');
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

describe('resolveDoctorSeverity', () => {
  it('maps verified to ok', () => {
    expect(resolveDoctorSeverity('verified', true)).toBe('ok');
  });

  it('maps unverifiable-but-valid codes to warn', () => {
    expect(resolveDoctorSeverity('token_valid', true)).toBe('warn');
    expect(resolveDoctorSeverity('token_env', false)).toBe('warn');
  });

  it('maps failure codes to error', () => {
    expect(resolveDoctorSeverity('config_file_missing', false)).toBe('error');
    expect(resolveDoctorSeverity('entry_missing', false)).toBe('error');
    expect(resolveDoctorSeverity('token_missing', false)).toBe('error');
    expect(resolveDoctorSeverity('token_mismatch', false)).toBe('error');
    expect(resolveDoctorSeverity('file_unreadable', false)).toBe('error');
  });

  it('falls back to the healthy flag for unknown detail codes', () => {
    expect(resolveDoctorSeverity('unknown', false)).toBe('error');
    expect(resolveDoctorSeverity('unknown', true)).toBe('ok');
  });
});

describe('resolveDoctorStatusKey', () => {
  it('reports unknown when no check has run yet', () => {
    expect(resolveDoctorStatusKey(false, 'ok')).toBe('doctorStatusUnknown');
    expect(resolveDoctorStatusKey(false, 'error')).toBe('doctorStatusUnknown');
  });

  it('mirrors the severity tri-state for a checked connector', () => {
    expect(resolveDoctorStatusKey(true, 'ok')).toBe('doctorStatusOk');
    expect(resolveDoctorStatusKey(true, 'warn')).toBe('doctorStatusWarn');
    expect(resolveDoctorStatusKey(true, 'error')).toBe('doctorStatusFail');
  });
});
