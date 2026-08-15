/**
 * [INPUT]
 * #locales/*.json::connectWizard.doctor* (POS: Doctor detail i18n message keys)
 *
 * [OUTPUT]
 * resolveDoctorMessageKey
 *
 * [POS]
 * Maps server doctor detail codes to connectWizard i18n message keys so that
 * ConnectSection and ConnectWizardDialog render consistent, localized doctor
 * outcomes without duplicating the code-to-key table.
 */

/** Server doctor detail code → connectWizard message key. */
const DOCTOR_DETAIL_MESSAGE_KEYS: Record<string, string> = {
  verified: 'doctorHealthyVerified',
  token_valid: 'doctorHealthyTokenValid',
  config_file_missing: 'doctorDetailConfigMissing',
  entry_missing: 'doctorDetailEntryMissing',
  token_mismatch: 'doctorDetailTokenMismatch',
  file_unreadable: 'doctorDetailFileUnreadable',
};

/**
 * Resolve the localized message key for a doctor check outcome.
 * Falls back to the generic healthy/unhealthy key for unknown detail codes.
 */
export function resolveDoctorMessageKey(detail: string, healthy: boolean): string {
  return DOCTOR_DETAIL_MESSAGE_KEYS[detail] ?? (healthy ? 'doctorHealthy' : 'doctorUnhealthy');
}
