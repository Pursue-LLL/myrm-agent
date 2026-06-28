import { apiRequest } from '@/lib/api';

// ==================== Types ====================

export type JobStatus = 'active' | 'paused' | 'completed';
export type RunStatus = 'ok' | 'error' | 'skipped';
export type SessionTarget = 'isolated' | 'main' | 'daily';

export interface CronSchedule {
  kind: 'cron' | 'interval' | 'once';
  expr?: string;
  tz?: string;
  interval_ms?: number;
  run_at?: string;
  stagger_ms?: number;
}

export interface CronDelivery {
  channel: string;
  target?: string | null;
  secret?: string | null;
}

export interface ActiveHours {
  start: string;
  end: string;
  tz: string;
}

export interface MonitorConfig {
  monitor_type: 'set' | 'hash' | 'timeseries';
  ttl_days: number;
  enabled: boolean;
  last_reset_at?: string | null;
  last_reset_reason?: string | null;
}

export interface FailureAlertConfig {
  enabled: boolean;
  after: number;
  cooldown_seconds: number;
  delivery?: CronDelivery | null;
}

export interface EventTrigger {
  pattern: string;
  channel?: string | null;
}

export interface SystemEventTrigger {
  source: string;
  event_type: string;
  filters: Record<string, string>;
}

export interface WebhookTrigger {
  path?: string | null;
  secret?: string | null;
}

export interface TriggerConfig {
  webhooks: WebhookTrigger[];
  events: EventTrigger[];
  system_events: SystemEventTrigger[];
}

export interface CronJob {
  id: string;
  user_id: string;
  name: string;
  job_type: 'agent' | 'shell' | 'router';
  status: JobStatus;
  schedule: CronSchedule;
  prompt?: string;
  model?: string;
  chat_id?: string;
  agent_id?: string | null;
  command?: string;
  delivery?: CronDelivery;
  failure_delivery?: CronDelivery | null;
  failure_alert?: FailureAlertConfig | false | null;
  active_hours?: ActiveHours | null;
  triggers?: TriggerConfig | null;
  context_from: string[];
  pre_condition_script?: string | null;
  max_retries: number;
  retry_backoff_ms: number;
  timeout_seconds: number;
  misfire_grace_seconds: number;
  cooldown_seconds: number;
  max_fires?: number | null;
  expires_at?: string | null;
  fire_count: number;
  session_target: SessionTarget;
  required_capabilities: string[];
  allowed_roots: string[];
  delete_after_run: boolean;
  run_retention_days: number;
  deduplicate: boolean;
  skip_if_active: boolean;
  monitor_config?: MonitorConfig | null;
  next_run_at?: string;
  last_run_at?: string;
  last_status?: RunStatus;
  last_error?: string;
  consecutive_failures: number;
  last_failure_alert_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CronRun {
  id: string;
  job_id: string;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  status: RunStatus;
  output?: string;
  error?: string;
  model?: string;
  usage_input_tokens?: number;
  usage_output_tokens?: number;
  usage_total_tokens?: number;
  trigger_source?: string | null;
  delivery_status?: 'delivered' | 'failed' | 'skipped';
  delivery_error?: string;
  job_name?: string;
}

export interface CronJobsListResponse {
  items: CronJob[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface CronRunsListResponse {
  items: CronRun[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface UsageSummary {
  total_runs: number;
  success_runs: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  avg_tokens_per_run: number;
}

export interface UsageByDay {
  date: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  runs: number;
}

export interface UsageByJob {
  job_id: string;
  job_name: string;
  total_tokens: number;
  runs: number;
}

export interface UsageByModel {
  model: string;
  total_tokens: number;
  runs: number;
}

export interface UsageStatsResponse {
  summary: UsageSummary;
  by_day: UsageByDay[];
  by_job: UsageByJob[];
  by_model: UsageByModel[];
}

export interface TriggerConfigRequest {
  webhooks?: Record<string, never>[];
  events?: { pattern: string; channel?: string }[];
  system_events?: { source: string; event_type: string; filters?: Record<string, string> }[];
}

export interface CreateCronJobRequest {
  name: string;
  job_type: 'agent' | 'shell' | 'router';
  schedule: CronSchedule;
  prompt?: string;
  model?: string;
  agent_id?: string;
  command?: string;
  delivery?: { channel: string; target?: string };
  failure_delivery?: { channel: string; target?: string };
  failure_alert?: {
    enabled: boolean;
    after?: number;
    cooldown_seconds?: number;
    delivery?: CronDelivery;
  };
  active_hours?: ActiveHours;
  triggers?: TriggerConfigRequest;
  max_retries?: number;
  retry_backoff_ms?: number;
  timeout_seconds?: number;
  misfire_grace_seconds?: number;
  cooldown_seconds?: number;
  max_fires?: number;
  expires_at?: string;
  session_target?: SessionTarget;
  delete_after_run?: boolean;
  run_retention_days?: number;
  deduplicate?: boolean;
  skip_if_active?: boolean;
  monitor_config?: MonitorConfig;
  context_from?: string[];
  pre_condition_script?: string | null;
}

export interface UpdateCronJobRequest {
  name?: string;
  status?: JobStatus;
  schedule?: CronSchedule;
  prompt?: string;
  model?: string;
  agent_id?: string | null;
  command?: string;
  delivery?: { channel: string; target?: string };
  failure_delivery?: { channel: string; target?: string } | null;
  failure_alert?:
    | { enabled: boolean; after?: number; cooldown_seconds?: number; delivery?: CronDelivery }
    | false
    | null;
  active_hours?: ActiveHours | null;
  triggers?: TriggerConfigRequest | null;
  max_retries?: number;
  retry_backoff_ms?: number;
  timeout_seconds?: number;
  misfire_grace_seconds?: number;
  cooldown_seconds?: number;
  max_fires?: number | null;
  expires_at?: string | null;
  session_target?: SessionTarget;
  chat_id?: string | null;
  required_capabilities?: string[];
  allowed_roots?: string[];
  delete_after_run?: boolean;
  run_retention_days?: number;
  deduplicate?: boolean;
  skip_if_active?: boolean;
  monitor_config?: MonitorConfig | null;
  context_from?: string[];
  pre_condition_script?: string | null;
}

// ==================== API ====================

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

// ==================== Blueprints ====================

export interface BlueprintSlotDef {
  name: string;
  type: 'time' | 'text' | 'enum';
  label: string;
  default: string;
  options: string[];
}

export interface BlueprintDef {
  id: string;
  icon: string;
  title: Record<string, string>;
  description: Record<string, string>;
  prompt_template: Record<string, string>;
  slots: BlueprintSlotDef[];
  category: string;
  tags: string[];
  sort_order: number;
}

export interface BlueprintFillResponse {
  schedule: CronSchedule;
  prompt: string;
  name: string;
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
