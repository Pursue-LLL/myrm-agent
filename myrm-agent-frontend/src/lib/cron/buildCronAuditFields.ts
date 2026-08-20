/**
 * [INPUT]
 * @/services/cron.types::CronJob (POS: Frontend Cron job type definitions)
 *
 * [OUTPUT]
 * buildCronAuditFields / isCronAuditConfirmed / markCronAuditConfirmed
 *
 * [POS]
 * Pure helpers for Hermes-style six-field cron create audit snapshots and confirm gate storage.
 */

import type { CronJob, CronSchedule } from '@/services/cron.types';

export interface CronAuditField {
  id: string;
  value: string;
}

function formatSchedule(schedule: CronSchedule): string {
  if (schedule.kind === 'cron') {
    const tz = schedule.tz ?? 'UTC';
    return `${schedule.expr ?? '—'} (${tz})`;
  }
  if (schedule.kind === 'interval') {
    const mins = Math.round((schedule.interval_ms ?? 0) / 60_000);
    const tz = schedule.tz ?? 'UTC';
    return `every ${mins}m (${tz})`;
  }
  if (schedule.kind === 'once') {
    return schedule.run_at ?? '—';
  }
  return '—';
}

function summarizeSkills(job: CronJob): string {
  if (job.tools_allowed.length > 0) {
    return job.tools_allowed.join(', ');
  }
  if (job.agent_id) {
    return `agent:${job.agent_id}`;
  }
  if (job.job_type === 'shell') {
    return 'shell (no skill binding)';
  }
  if (job.job_type === 'router') {
    return 'router script gate';
  }
  if (job.job_type === 'reminder') {
    return 'reminder (prompt only)';
  }
  return 'default agent toolkit';
}

function summarizeInputs(job: CronJob): string {
  const parts: string[] = [];
  if (job.context_from.length > 0) {
    parts.push(`context_from: ${job.context_from.join(', ')}`);
  }
  if (job.prompt?.trim()) {
    const snippet = job.prompt.trim().slice(0, 120);
    parts.push(`prompt: ${snippet}${job.prompt.length > 120 ? '…' : ''}`);
  }
  if (job.command?.trim()) {
    parts.push(`command: ${job.command.trim().slice(0, 80)}`);
  }
  if (job.pre_condition_script?.trim()) {
    parts.push('pre_condition_script configured');
  }
  if (parts.length === 0) {
    return 'inline prompt / agent context';
  }
  return parts.join(' · ');
}

function summarizeOutputs(job: CronJob): string {
  const parts: string[] = [];
  parts.push(`session: ${job.session_target}`);
  if (job.chat_id) {
    parts.push(`chat: ${job.chat_id}`);
  }
  const channel = job.delivery?.channel ?? 'chat';
  const target = job.delivery?.target?.trim();
  parts.push(target ? `delivery: ${channel} → ${target}` : `delivery: ${channel}`);
  if (job.acceptance_criteria && job.acceptance_criteria.length > 0) {
    parts.push(`acceptance: ${job.acceptance_criteria.length} rule(s)`);
  }
  return parts.join(' · ');
}

function summarizeFailureTrail(job: CronJob): string {
  const parts: string[] = [];
  parts.push(`retention: ${job.run_retention_days}d runs`);
  if (job.failure_alert && typeof job.failure_alert === 'object' && job.failure_alert.enabled) {
    parts.push(`alert after ${job.failure_alert.after} failures`);
  }
  if (job.failure_delivery?.channel) {
    const target = job.failure_delivery.target?.trim();
    parts.push(
      target
        ? `failure_delivery: ${job.failure_delivery.channel} → ${target}`
        : `failure_delivery: ${job.failure_delivery.channel}`,
    );
  }
  if (job.consecutive_failures > 0) {
    parts.push(`consecutive_failures: ${job.consecutive_failures}`);
  }
  if (job.last_error?.trim()) {
    parts.push(`last_error: ${job.last_error.trim().slice(0, 80)}`);
  }
  return parts.join(' · ');
}

/** Build the six Hermes-style cron audit fields from a full CronJob snapshot. */
export function buildCronAuditFields(job: CronJob): CronAuditField[] {
  return [
    { id: 'taskName', value: job.name },
    { id: 'scheduleTz', value: formatSchedule(job.schedule) },
    { id: 'skillsInvoked', value: summarizeSkills(job) },
    { id: 'inputSources', value: summarizeInputs(job) },
    { id: 'outputDestinations', value: summarizeOutputs(job) },
    { id: 'failureRecords', value: summarizeFailureTrail(job) },
  ];
}

export const CRON_AUDIT_CONFIRM_STORAGE_PREFIX = 'myrm:cron-audit-confirmed:';

export function isCronAuditConfirmed(jobId: string): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  return window.localStorage.getItem(`${CRON_AUDIT_CONFIRM_STORAGE_PREFIX}${jobId}`) === '1';
}

export function markCronAuditConfirmed(jobId: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(`${CRON_AUDIT_CONFIRM_STORAGE_PREFIX}${jobId}`, '1');
}
