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

export interface PollTrigger {
  url: string;
  json_path?: string | null;
  interval_seconds: number;
  change_detection: boolean;
}

export interface StreamTrigger {
  url: string;
  protocol: 'ws' | 'sse';
  filter_json_path?: string | null;
  filter_regex?: string | null;
  headers?: Record<string, string>;
}

export interface TriggerConfig {
  webhooks: WebhookTrigger[];
  events: EventTrigger[];
  system_events: SystemEventTrigger[];
  polls: PollTrigger[];
  streams: StreamTrigger[];
}

export interface CronJob {
  id: string;
  user_id: string;
  name: string;
  job_type: 'agent' | 'shell' | 'router' | 'reminder';
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
  tools_allowed: string[];
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

export interface CronRunVerification {
  status: 'pass' | 'fail' | 'skipped' | 'error';
  passed?: boolean | null;
  summary?: string;
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
  metadata?: {
    verification?: CronRunVerification;
  };
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
  polls?: { url: string; json_path?: string; interval_seconds?: number; change_detection?: boolean }[];
  streams?: {
    url: string;
    protocol?: 'ws' | 'sse';
    filter_json_path?: string;
    filter_regex?: string;
    headers?: Record<string, string>;
  }[];
}

export interface CreateCronJobRequest {
  name: string;
  job_type: 'agent' | 'shell' | 'router' | 'reminder';
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
  required_capabilities?: string[];
  tools_allowed?: string[];
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
  tools_allowed?: string[];
  allowed_roots?: string[];
  delete_after_run?: boolean;
  run_retention_days?: number;
  deduplicate?: boolean;
  skip_if_active?: boolean;
  monitor_config?: MonitorConfig | null;
  context_from?: string[];
  pre_condition_script?: string | null;
}

export interface BlueprintSlotDef {
  name: string;
  type: 'time' | 'text' | 'enum';
  label: string;
  default: string;
  options: string[];
  optional: boolean;
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
  required_capabilities: string[];
  tools_allowed: string[];
}
