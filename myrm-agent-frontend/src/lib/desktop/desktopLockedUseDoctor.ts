/**
 * [INPUT]
 * - @/services/runtime-health (POS: DoctorResponse / HealthReport contract)
 *
 * [OUTPUT]
 * - findDesktopLockedUseReport: locate server-layer DesktopLockedUse probe
 * - lockedUseDoctorToneFromStatus: map HealthStatus to UI tone
 * - resolveLockedUseDoctorDetailKey / resolveLockedUseDoctorBadgeKey / resolveLockedUseDoctorVisualTone
 * - readLockedUseEnabledFromReport
 *
 * [POS]
 * SSOT for wiring `/health/doctor` DesktopLockedUse into settings surfaces.
 */

import type { DoctorResponse, HealthReport } from '@/services/runtime-health';

export type LockedUseDoctorTone =
  | 'loading'
  | 'pass'
  | 'pass_bridge'
  | 'warn'
  | 'fail'
  | 'unavailable';

export function readLockedUseEnabledFromReport(report: HealthReport | null): boolean | null {
  const raw = report?.meta_data?.locked_use_enabled;
  return typeof raw === 'boolean' ? raw : null;
}

/** Badge i18n key under settings.desktopPermissions. */
export function resolveLockedUseDoctorBadgeKey(
  report: HealthReport | null,
  isLoading: boolean,
): string {
  if (isLoading) {
    return 'lockedUseDoctorBadgeLoading';
  }
  if (!report) {
    return 'lockedUseDoctorUnavailable';
  }
  if (report.status === 'warn') {
    return 'lockedUseDoctorWarn';
  }
  if (report.status === 'fail') {
    return 'lockedUseDoctorFail';
  }
  if (report.status === 'pass') {
    if (report.code === 'OK_DESKTOP_LOCKED_USE_N_A') {
      return 'lockedUseDoctorBadgeNotMac';
    }
    if (readLockedUseEnabledFromReport(report) === true) {
      return 'lockedUseDoctorBadgeAwayOn';
    }
    return 'lockedUseDoctorBadgeBridgeReady';
  }
  return 'lockedUseDoctorUnavailable';
}

export function resolveLockedUseDoctorVisualTone(
  report: HealthReport | null,
  isLoading: boolean,
): LockedUseDoctorTone {
  if (isLoading) {
    return 'loading';
  }
  if (!report) {
    return 'unavailable';
  }
  if (report.status === 'warn') {
    return 'warn';
  }
  if (report.status === 'fail') {
    return 'fail';
  }
  if (report.status === 'pass') {
    if (report.code === 'OK_DESKTOP_LOCKED_USE_N_A') {
      return 'pass_bridge';
    }
    if (readLockedUseEnabledFromReport(report) === true) {
      return 'pass';
    }
    return 'pass_bridge';
  }
  return 'unavailable';
}

export function findDesktopLockedUseReport(doctor: DoctorResponse | null): HealthReport | null {
  if (!doctor) {
    return null;
  }
  const fromServer = doctor.server.find((r) => r.component_name === 'DesktopLockedUse');
  if (fromServer) {
    return fromServer;
  }
  return doctor.harness.find((r) => r.component_name === 'DesktopLockedUse') ?? null;
}

/** User-facing detail line for settings UI; null when no extra copy is needed. */
export function resolveLockedUseDoctorDetailKey(report: HealthReport | null): string | null {
  if (!report) {
    return null;
  }
  if (report.status === 'pass') {
    if (report.code === 'OK_DESKTOP_LOCKED_USE_N_A') {
      return 'lockedUseDoctorDetailNotMac';
    }
    if (readLockedUseEnabledFromReport(report) === true) {
      return null;
    }
    return 'lockedUseDoctorDetailAwayOff';
  }
  switch (report.code) {
    case 'WARN_CURTAIN_BRIDGE_MISSING':
    case 'ERR_CURTAIN_BRIDGE_MISSING':
      return 'lockedUseDoctorDetailBridgeMissing';
    case 'ERR_DESKTOP_SHELL_UNAVAILABLE':
      return 'lockedUseDoctorDetailShellUnavailable';
    default:
      return 'lockedUseDoctorDetailGeneric';
  }
}

export function lockedUseDoctorNeedsSettingsLink(report: HealthReport | null): boolean {
  return report?.status === 'warn' || report?.status === 'fail';
}
