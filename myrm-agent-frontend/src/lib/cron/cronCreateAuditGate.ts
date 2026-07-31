/**
 * [INPUT]
 * @/services/cron::{pauseCronJob, resumeCronJob, getCronJob} (POS: Frontend Cron API client)
 * @/services/cron.types::CronJob (POS: Cron job type definitions)
 *
 * [OUTPUT]
 * needsSettingsAuditGate / canDismissSettingsAuditFlow /
 * prepareJobForSettingsAudit / resumeJobAfterAuditConfirm
 *
 * [POS]
 * Settings cron create audit gate — pause new jobs until the user confirms the audit panel.
 */

import { getCronJob, pauseCronJob, resumeCronJob } from '@/services/cron';
import type { CronJob } from '@/services/cron.types';
import { isCronAuditConfirmed } from '@/lib/cron/buildCronAuditFields';

/** Settings detail/create: paused job awaiting user confirm + resume. */
export function needsSettingsAuditGate(job: CronJob): boolean {
  return job.status === 'paused' && !isCronAuditConfirmed(job.id);
}

/** Settings audit dialog may close only after confirm and resume succeeded. */
export function canDismissSettingsAuditFlow(job: CronJob): boolean {
  return isCronAuditConfirmed(job.id) && job.status === 'active';
}

export async function prepareJobForSettingsAudit(job: CronJob): Promise<CronJob> {
  if (job.status !== 'active') {
    return job;
  }
  await pauseCronJob(job.id);
  return getCronJob(job.id);
}

export async function resumeJobAfterAuditConfirm(jobId: string): Promise<CronJob> {
  await resumeCronJob(jobId);
  return getCronJob(jobId);
}
