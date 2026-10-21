/**
 * petDoctor — Companion sprite health check client.
 *
 * [INPUT]
 * - @/lib/api::apiRequest (POS: frontend API layer; doctor route has no feature gate)
 *
 * [OUTPUT]
 * - fetchCompanionDoctor: GET /companion/doctor structured report
 * - openCompanionHealthCheck: open Pet Palette and expand embedded doctor panel
 *
 * [POS]
 * GUI troubleshooting for companion sprite install/render chain.
 */

import { apiRequest } from '@/lib/api';
import useCompanionStore from '@/store/useCompanionStore';

export type DoctorCheckStatus = 'pass' | 'warn' | 'fail';

export interface CompanionDoctorCheck {
  id: string;
  status: DoctorCheckStatus;
  message: string;
  fixAction: string | null;
}

export interface CompanionDoctorReport {
  ready: boolean;
  checks: CompanionDoctorCheck[];
  activeSlug: string | null;
  installedCount: number;
}

interface CompanionDoctorCheckRaw {
  id: string;
  status: DoctorCheckStatus;
  message: string;
  fix_action?: string | null;
  fixAction?: string | null;
}

interface CompanionDoctorReportRaw {
  ready: boolean;
  checks: CompanionDoctorCheckRaw[];
  active_slug?: string | null;
  activeSlug?: string | null;
  installed_count?: number;
  installedCount?: number;
}

export async function fetchCompanionDoctor(rescan = false): Promise<CompanionDoctorReport> {
  const query = rescan ? '?rescan=true' : '';
  const data = await apiRequest<CompanionDoctorReportRaw>(`/companion/doctor${query}`, {
    silent: true,
  });
  return {
    ready: Boolean(data.ready),
    checks: (Array.isArray(data.checks) ? data.checks : []).map((check) => ({
      id: check.id,
      status: check.status,
      message: check.message,
      fixAction: check.fixAction ?? check.fix_action ?? null,
    })),
    activeSlug: data.activeSlug ?? data.active_slug ?? null,
    installedCount:
      typeof data.installedCount === 'number'
        ? data.installedCount
        : typeof data.installed_count === 'number'
          ? data.installed_count
          : 0,
  };
}

export function openCompanionHealthCheck(): void {
  useCompanionStore.getState().openCompanionHealthCheck();
}
