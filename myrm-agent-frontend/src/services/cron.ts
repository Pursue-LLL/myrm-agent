import { apiRequest } from '@/lib/api';

export type {
  ActiveHours,
  BlueprintDef,
  BlueprintFillResponse,
  BlueprintSlotDef,
  CreateCronJobRequest,
  CronDelivery,
  CronJob,
  CronJobsListResponse,
  CronRun,
  CronRunsListResponse,
  CronSchedule,
  EventTrigger,
  FailureAlertConfig,
  JobStatus,
  MonitorConfig,
  PollTrigger,
  RunStatus,
  SessionTarget,
  StreamTrigger,
  SystemEventTrigger,
  TriggerConfig,
  TriggerConfigRequest,
  UpdateCronJobRequest,
  UsageByDay,
  UsageByJob,
  UsageByModel,
  UsageStatsResponse,
  UsageSummary,
  WebhookTrigger,
} from './cron.types';

import type {
  BlueprintDef,
  BlueprintFillResponse,
  CreateCronJobRequest,
  CronJob,
  CronJobsListResponse,
  CronRunsListResponse,
  UpdateCronJobRequest,
  UsageStatsResponse,
} from './cron.types';

export async function listCronJobs(params?: {
  limit?: number;
  offset?: number;
  search?: string;
}): Promise<CronJobsListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set('limit', String(params.limit));
  if (params?.offset) query.set('offset', String(params.offset));
  if (params?.search) query.set('search', params.search);
  const qs = query.toString();
  return apiRequest(`/cron${qs ? `?${qs}` : ''}`);
}

export async function createCronJob(data: CreateCronJobRequest): Promise<CronJob> {
  return apiRequest('/cron', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function updateCronJob(id: string, data: UpdateCronJobRequest): Promise<CronJob> {
  return apiRequest(`/cron/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function deleteCronJob(id: string): Promise<void> {
  return apiRequest(`/cron/${id}`, { method: 'DELETE' });
}

export async function pauseCronJob(id: string): Promise<CronJob> {
  return apiRequest(`/cron/${id}/pause`, { method: 'POST' });
}

export async function resumeCronJob(id: string): Promise<CronJob> {
  return apiRequest(`/cron/${id}/resume`, { method: 'POST' });
}

export async function triggerCronJob(id: string): Promise<void> {
  return apiRequest(`/cron/${id}/trigger`, { method: 'POST' });
}

export async function duplicateCronJob(id: string): Promise<CronJob> {
  return apiRequest(`/cron/${id}/duplicate`, { method: 'POST' });
}

export async function resetMonitorBaseline(id: string): Promise<void> {
  return apiRequest(`/cron/${id}/reset-baseline`, { method: 'POST' });
}

export async function listCronRuns(
  jobId: string,
  params?: { limit?: number; offset?: number; status?: string },
): Promise<CronRunsListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set('limit', String(params.limit));
  if (params?.offset) query.set('offset', String(params.offset));
  if (params?.status) query.set('status', params.status);
  return apiRequest(`/cron/${jobId}/runs?${query.toString()}`);
}

export async function fetchUsageStats(days?: number): Promise<UsageStatsResponse> {
  const query = days !== undefined ? `?days=${days}` : '';
  return apiRequest(`/cron/stats/usage${query}`);
}

export async function listAllCronRuns(params?: {
  limit?: number;
  offset?: number;
  status?: string;
}): Promise<CronRunsListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set('limit', String(params.limit));
  if (params?.offset) query.set('offset', String(params.offset));
  if (params?.status) query.set('status', params.status);
  return apiRequest(`/cron/runs/all?${query.toString()}`);
}

export async function listBlueprints(): Promise<BlueprintDef[]> {
  return apiRequest('/cron/blueprints');
}

export async function fillBlueprint(
  blueprintId: string,
  values: Record<string, string>,
  locale?: string,
  tz?: string,
): Promise<BlueprintFillResponse> {
  return apiRequest('/cron/blueprints/fill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      blueprint_id: blueprintId,
      values,
      locale: locale || 'en',
      tz: tz || undefined,
    }),
  });
}
