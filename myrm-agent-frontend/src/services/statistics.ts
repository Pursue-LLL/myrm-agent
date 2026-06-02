/**
 * [INPUT]
 * - lib/api::apiRequest (POS: 前端 API 接入层。统一封装请求基址、超时、错误归一化、存储 URL 拼接以及安全拦截（全局强登出），避免脏配置污染请求链路。)
 * - services/contextHealth::ContextHealth (POS: Statistics context-health DTO layer. Defines compaction, pruning/archive restore, adaptive backoff, and prompt-cache health contracts for Session Analytics UI.)
 *
 * [OUTPUT]
 * - getUsageStatistics: retrieves global usage analytics.
 * - getSessionAnalytics: retrieves session analytics including context-health DTOs.
 *
 * [POS]
 * Statistics API client DTO layer. Defines usage, session analytics, and context-health response contracts.
 */

import { apiRequest } from '@/lib/api';
import type { ContextHealth } from './contextHealth';

export interface ModelBreakdown {
  calls: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  totalTokens: number;
  costUsd: number;
}

export interface TierStats {
  calls: number;
  totalTokens: number;
  costUsd: number;
}

export interface EstimatedSavings {
  actualCost: number;
  hypotheticalCost: number;
  savings: number;
  savingsPercent: number;
}

export interface UsageStats {
  calls: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  reasoningTokens: number;
  citationTokens: number;
  totalTokens: number;
  costUsd: number;
  cacheSavingsUsd?: number;
  cacheHitRate: number;
  modelBreakdown: Record<string, ModelBreakdown>;
  routingBreakdown?: Record<string, TierStats>;
  estimatedSavings?: EstimatedSavings;
  privacyRouteBreakdown?: Record<string, number>;
}

export interface DailyUsage {
  date: string;
  calls: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  reasoningTokens: number;
  citationTokens: number;
  totalTokens: number;
  costUsd: number;
  cacheSavingsUsd: number;
  cacheBreakCounts: Record<string, number>;
}

export interface DailyUsageResponse {
  days: number;
  start: string;
  end: string;
  daily: DailyUsage[];
}

export interface SessionUsage extends UsageStats {
  chatId: string;
  title: string;
  actionMode: string;
  createdAt: string | null;
  messageCount: number;
}

export interface SessionUsageResponse {
  sessions: SessionUsage[];
}

export interface DailyActivity {
  date: string;
  day_of_week: number;
  session_count: number;
  tool_calls: number;
  duration_ms: number;
}

/**
 * Global activity patterns across all sessions.
 * All time-based fields use UTC timezone for consistency.
 */
export interface GlobalActivityPatterns {
  timezone: string; // Timezone identifier (e.g., "UTC")
  daily_activities: DailyActivity[];
  by_day_of_week: Record<number, number>;
  by_hour: Record<number, number>;
  active_days: number;
  max_streak: number;
  busiest_day_of_week: number; // Day of week index (0=Monday, 6=Sunday)
  busiest_hour: number; // Hour of day (0-23, UTC)
}

export async function getUsageStatistics(start?: string, end?: string): Promise<UsageStats> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const query = params.toString();
  return apiRequest<UsageStats>(`/statistics/usage${query ? `?${query}` : ''}`);
}

export async function getDailyUsage(days = 30): Promise<DailyUsageResponse> {
  return apiRequest<DailyUsageResponse>(`/statistics/usage/daily?days=${days}`);
}

export async function getSessionUsage(limit = 20): Promise<SessionUsageResponse> {
  return apiRequest<SessionUsageResponse>(`/statistics/usage/sessions?limit=${limit}`);
}

export async function getGlobalActivityPatterns(timeRangeDays?: number): Promise<GlobalActivityPatterns> {
  const params = new URLSearchParams();
  if (timeRangeDays) params.set('time_range_days', timeRangeDays.toString());
  const query = params.toString();
  return apiRequest<GlobalActivityPatterns>(`/statistics/activity${query ? `?${query}` : ''}`);
}

export interface ToolStabilityDaily {
  date: string;
  tool_name: string;
  total_calls: number;
  success_count: number;
  failure_count: number;
  timeout_count: number;
  avg_duration_ms: number;
  p90_duration_ms: number;
  p99_duration_ms: number;
  failure_rate: number;
  failure_reasons: Record<string, number>;
}

export interface ToolStabilityAnalytics {
  daily_stability: ToolStabilityDaily[];
  global_total_calls: number;
  global_failure_rate: number;
  global_avg_duration_ms: number;
  busiest_tool: string;
  most_failed_tool: string;
}

export async function getToolStability(toolName?: string, timeRangeDays = 30): Promise<ToolStabilityAnalytics> {
  const params = new URLSearchParams();
  if (toolName) params.set('tool_name', toolName);
  params.set('time_range_days', timeRangeDays.toString());
  return apiRequest<ToolStabilityAnalytics>(`/statistics/tool-stability?${params.toString()}`);
}

/**
 * Top session record for Top N analytics (A3).
 */
export interface TopSession {
  session_id: string;
  metric_value: number;
  metric_type: 'duration' | 'messages' | 'tokens' | 'tool_calls';
  started_at: number; // UTC timestamp
  duration_ms: number;
  message_count: number;
  total_tokens: number;
  tool_calls: number;
}

export async function getTopSessions(
  metric: 'duration' | 'messages' | 'tokens' | 'tool_calls' = 'duration',
  limit = 10,
  timeRangeDays?: number,
): Promise<TopSession[]> {
  const params = new URLSearchParams();
  params.set('metric', metric);
  params.set('limit', limit.toString());
  if (timeRangeDays) params.set('time_range_days', timeRangeDays.toString());
  return apiRequest<TopSession[]>(`/statistics/top-sessions?${params.toString()}`);
}

/**
 * Tool breakdown for a session.
 */
export interface ToolBreakdown {
  tool_name: string;
  call_count: number;
  total_duration_ms: number;
}

/**
 * Event in session timeline.
 */
export interface SessionEvent {
  type: string;
  timestamp: number;
  data: Record<string, unknown>;
}

/**
 * Comprehensive analytics for a single session.
 */
export interface SessionAnalytics {
  session_id: string;
  title: string;
  action_mode: string;
  created_at: string | null;
  duration_ms: number;
  message_count: number;
  user_messages: number;
  assistant_messages: number;
  // Token & Cost
  calls: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  reasoningTokens: number;
  citationTokens: number;
  totalTokens: number;
  costUsd: number;
  cacheHitRate: number;
  modelBreakdown: Record<string, ModelBreakdown>;
  // Tool usage
  tool_breakdown: ToolBreakdown[];
  // Events timeline
  events_timeline: SessionEvent[];
  // Task metrics
  task_metrics: Record<string, unknown>;
  context_health: ContextHealth;
  token_economics?: TokenEconomicsSnapshot;
}

export interface TokenEconomicsSnapshot {
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cached_tokens?: number;
    reasoning_tokens?: number;
  };
  call_count: number;
  total_cost_usd: number;
  error_count: number;
  latency: {
    avg_ms: number;
    p95_ms: number;
    min_ms: number;
    max_ms: number;
    avg_ttft_ms: number;
    p95_ttft_ms: number;
    avg_tokens_per_second: number;
  };
  model_breakdown?: Record<
    string,
    {
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
      cost_usd: number;
    }
  >;
  tool_breakdown?: Record<
    string,
    {
      total_tokens: number;
      cost_usd: number;
    }
  >;
}

const sessionAnalyticsCache = new Map<string, { data: SessionAnalytics; timestamp: number }>();
const CACHE_TTL_MS = 30000; // 30 seconds

/**
 * Get comprehensive analytics for a single session.
 */
export async function getSessionAnalytics(sessionId: string, forceRefresh = false): Promise<SessionAnalytics> {
  const now = Date.now();
  if (!forceRefresh) {
    const cached = sessionAnalyticsCache.get(sessionId);
    if (cached && now - cached.timestamp < CACHE_TTL_MS) {
      return cached.data;
    }
  }
  const data = await apiRequest<SessionAnalytics>(`/statistics/session/${sessionId}`);
  sessionAnalyticsCache.set(sessionId, { data, timestamp: now });
  return data;
}

// ── Execution Trace (Task-level Replay) ─────────────────────────────

export type TraceOutcome = 'success' | 'failure' | 'cancelled' | 'unknown';

export interface TraceMetadata {
  user_id: string | null;
  agent_id: string | null;
  task_type: string | null;
  trace_id: string | null;
}

export interface TraceToolCall {
  sequence: number;
  tool_name: string;
  start_time: number;
  end_time: number | null;
  duration_ms: number | null;
  success: boolean;
  error: string | null;
  input_data?: Record<string, unknown>;
  output_summary?: string | null;
  output_data?: unknown;
}

export interface TraceLLMCall {
  sequence: number;
  start_time: number;
  end_time?: number | null;
  model_name: string | null;
  prompt_preview?: string | null;
  message_count?: number;
  duration_ms: number | null;
  ttft_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface TraceMemoryEvent {
  id: string;
  phase: string;
  status: string;
  timestamp: number;
  title: string;
  summary: string;
  target_kind: string | null;
  target_id: string | null;
  influence_count: number;
}

export interface TraceError {
  timestamp: number;
  error: string;
  error_type: string;
}

export interface TraceHumanFeedback {
  timestamp: number;
  tool_name: string | null;
  action: string | null;
  approved: boolean | null;
}

export interface ExecutionTrace {
  session_id: string;
  metadata: TraceMetadata;
  outcome: TraceOutcome;
  start_time: number;
  end_time: number;
  duration_ms: number;
  task_input: string;
  output: string;
  tool_calls: TraceToolCall[];
  llm_calls: TraceLLMCall[];
  errors: TraceError[];
  human_feedback: TraceHumanFeedback[];
  memory_events?: TraceMemoryEvent[];
  total_events: number;
  total_tokens: number;
}

export async function getSessionExecutionTrace(sessionId: string): Promise<ExecutionTrace> {
  return apiRequest<ExecutionTrace>(`/statistics/session/${sessionId}/trace`);
}

// ── Growth Dashboard ────────────────────────────────────────────────

export interface GrowthSnapshot {
  total_memories: number;
  memory_by_type: Record<string, number>;
  memory_week_delta: number;
  total_skills: number;
  total_evolutions: number;
  evolutions_approved: number;
  evolutions_rejected: number;
  evolutions_pending: number;
  evolutions_apply_failed: number;
  active_days: number;
  max_streak: number;
  memory_health_score: number;
  memory_health_dimensions: Record<string, number>;
}

export interface ActivityDay {
  date: string;
  count: number;
}

export interface WeeklySummary {
  cron_executions: number;
  conversations: number;
  messages_sent: number;
  tool_calls: number;

  previous_cron_executions: number;
  previous_conversations: number;
  previous_messages_sent: number;
  previous_tool_calls: number;
}

export interface SkillEvolutionEvent {
  skill_id: string | null;
  skill_name: string;
  source: 'draft' | 'evolution';
  status:
    | 'PENDING_REVIEW'
    | 'AUTO_APPLIED'
    | 'FAILED_SCAN'
    | 'BLOCKED_LOCKED'
    | 'APPROVED'
    | 'REJECTED'
    | 'APPLY_FAILED';
  growth_type: string;
  created_at: string;
  change_summary: string;
}

export interface GrowthDashboardData {
  snapshot: GrowthSnapshot;
  activity_heatmap: ActivityDay[];
  weekly_summary: WeeklySummary;
  skill_events: SkillEvolutionEvent[];
}

export async function getGrowthDashboard(days = 84): Promise<GrowthDashboardData> {
  return apiRequest<GrowthDashboardData>(`/statistics/growth-dashboard?days=${days}`);
}

// ── Model-Specific Session Drilldown ────────────────────────────────
export interface ModelSessionItem {
  chatId: string;
  title: string;
  actionMode: string;
  createdAt: string | null;
  calls: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  totalTokens: number;
  costUsd: number;
  lastUsedAt: string | null;
}

export async function getModelSessions(model: string, days = 30): Promise<ModelSessionItem[]> {
  return apiRequest<ModelSessionItem[]>(
    `/statistics/usage/model-sessions?model=${encodeURIComponent(model)}&days=${days}`,
  );
}

// ── Daily Journal ───────────────────────────────────────────────────

export interface DailyJournalSession {
  chat_id: string;
  title: string;
  action_mode: string;
  source: string;
  agent_id: string | null;
  started_at: string | null;
  message_count: number;
  total_tokens: number;
  total_usd: number;
  total_calls: number;
}

export interface DailyJournalApproval {
  id: string;
  action_type: string;
  status: string;
  severity: string;
  reason: string;
  created_at: string | null;
  resolved_at: string | null;
}

export interface DailyJournalCronRun {
  id: string;
  job_id: string;
  status: string;
  duration_ms: number;
  started_at: string | null;
  tokens: number;
  trigger_source: string | null;
}

export interface DailyJournalKanbanEvent {
  id: number;
  task_id: string;
  kind: string;
  created_at: string | null;
}

export interface DailyJournalTimelineItem {
  time: string | null;
  type: 'session' | 'approval' | 'cron_run' | 'kanban';
  title: string;
  detail: Record<string, unknown>;
}

export interface DailyJournalOverview {
  total_sessions: number;
  total_tokens: number;
  total_cost_usd: number;
  total_tool_calls: number;
  total_approvals: number;
  total_cron_runs: number;
  total_kanban_events: number;
  sessions_by_source: Record<string, number>;
}

export interface DailyJournalData {
  date: string;
  overview: DailyJournalOverview;
  sessions: DailyJournalSession[];
  approvals: DailyJournalApproval[];
  cron_runs: DailyJournalCronRun[];
  kanban_events: DailyJournalKanbanEvent[];
  timeline: DailyJournalTimelineItem[];
}

export async function getDailyJournal(date: string, agentId?: string): Promise<DailyJournalData> {
  const params = new URLSearchParams({ date });
  if (agentId) params.set('agent_id', agentId);
  return apiRequest<DailyJournalData>(`/statistics/daily-journal?${params.toString()}`);
}
