/**
 * [INPUT]
 * - CompanionDoctorCheck id/status from GET /companion/doctor
 * - Optional report context (activeSlug, installedCount)
 *
 * [OUTPUT]
 * - localizeDoctorCheckMessage: user-facing check copy under companion.doctor.serverChecks.*
 *
 * [POS]
 * Maps stable server check ids to i18n keys; falls back to server message for dynamic atlas errors.
 */

import type { CompanionDoctorCheck, DoctorCheckStatus } from '@/services/companion/petDoctor';

export interface DoctorCheckMessageContext {
  activeSlug?: string | null;
  installedCount?: number;
}

function checkIdToKeySegment(id: string): string {
  return id.replace(/\./g, '_');
}

export function doctorCheckMessageKey(id: string, status: DoctorCheckStatus): string {
  return `doctor.serverChecks.${checkIdToKeySegment(id)}.${status}`;
}

export function localizeDoctorCheckMessage(
  translate: (key: string, values?: Record<string, string | number>) => string,
  check: CompanionDoctorCheck,
  context: DoctorCheckMessageContext,
): string {
  const key = doctorCheckMessageKey(check.id, check.status);
  const values: Record<string, string | number> = {};

  if (context.activeSlug && (check.id === 'config.sprite.slug' || check.id === 'disk.active_pet_files')) {
    values.slug = context.activeSlug;
  }
  if (check.id === 'disk.installed_pets' && typeof context.installedCount === 'number') {
    values.count = context.installedCount;
  }

  const localized = translate(key, values);
  if (localized === key) {
    return check.message;
  }
  return localized;
}
