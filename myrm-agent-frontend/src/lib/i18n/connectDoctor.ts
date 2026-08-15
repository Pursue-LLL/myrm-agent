/**
 * [INPUT]
 * #locales/*.json::connectWizard.doctor* (POS: Doctor detail i18n message keys)
 *
 * [OUTPUT]
 * - resolveDoctorMessageKey
 * - resolveDoctorSeverity
 * - formatDoctorRelativeTime
 *
 * [POS]
 * Maps server doctor detail codes to connectWizard i18n message keys and a
 * severity level so that ConnectSection and ConnectWizardDialog render
 * consistent, localized doctor outcomes without duplicating the tables.
 *
 * Severity is three-valued because a doctor result is not binary: some codes
 * report a healthy-but-unverifiable state (token_valid, token_env) that must
 * not be shown as a green "all good" nor as a red failure.
 */

import { formatDistanceToNow } from 'date-fns';
import { de, enUS, ja, ko, zhCN, zhTW } from 'date-fns/locale';

export type DoctorSeverity = 'ok' | 'warn' | 'error';

/** Server doctor detail code → connectWizard message key. */
const DOCTOR_DETAIL_MESSAGE_KEYS: Record<string, string> = {
  verified: 'doctorHealthyVerified',
  token_valid: 'doctorHealthyTokenValid',
  token_env: 'doctorDetailTokenEnv',
  token_missing: 'doctorDetailTokenMissing',
  config_file_missing: 'doctorDetailConfigMissing',
  entry_missing: 'doctorDetailEntryMissing',
  token_mismatch: 'doctorDetailTokenMismatch',
  file_unreadable: 'doctorDetailFileUnreadable',
};

/** Server doctor detail code → presentation severity (falls back to healthy flag). */
const DOCTOR_DETAIL_SEVERITIES: Record<string, DoctorSeverity> = {
  verified: 'ok',
  token_valid: 'warn',
  token_env: 'warn',
  config_file_missing: 'error',
  entry_missing: 'error',
  token_missing: 'error',
  token_mismatch: 'error',
  file_unreadable: 'error',
};

/**
 * Resolve the localized message key for a doctor check outcome.
 * Falls back to the generic healthy/unhealthy key for unknown detail codes.
 */
export function resolveDoctorMessageKey(detail: string, healthy: boolean): string {
  return DOCTOR_DETAIL_MESSAGE_KEYS[detail] ?? (healthy ? 'doctorHealthy' : 'doctorUnhealthy');
}

/**
 * Resolve the presentation severity for a doctor check outcome.
 * Falls back to the healthy flag for unknown detail codes.
 */
export function resolveDoctorSeverity(detail: string, healthy: boolean): DoctorSeverity {
  return DOCTOR_DETAIL_SEVERITIES[detail] ?? (healthy ? 'ok' : 'error');
}

const RELATIVE_LOCALES: Record<string, import('date-fns').Locale> = {
  zh: zhCN,
  'zh-TW': zhTW,
  en: enUS,
  ja,
  ko,
  de,
};

/**
 * Format an ISO timestamp as a localized relative time ("2 hours ago").
 * Returns an empty string for invalid timestamps.
 */
export function formatDoctorRelativeTime(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return formatDistanceToNow(date, { addSuffix: true, locale: RELATIVE_LOCALES[locale] ?? enUS });
}
