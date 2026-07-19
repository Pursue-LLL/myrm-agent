/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Memory API DTOs and request helpers for memory CRUD, export, guardian health/policy/digest,
 * rating, status, and taste summary.
 *
 * [POS]
 * Frontend Memory API client. Owns typed HTTP contracts for user memory CRUD and lightweight memory governance.
 */

import { apiRequest } from '@/lib/api';

// ==================== 类型定义 ====================

export type MemoryType = 'profile' | 'semantic' | 'episodic' | 'procedural' | 'conversation' | 'claim' | 'task_digest';

export type MemoryStatusType = 'active' | 'disabled' | 'archived';

export type PendingMemoryStatus = 'pending' | 'approved' | 'rejected';

export type ConflictResolution = 'keep_old' | 'keep_new' | 'merge' | 'discard_both';

export interface PendingMemory {
  id: string;
  user_id: string;
  memory_type: MemoryType;
  content: string;
  extra_data?: Record<string, unknown>;
  source_chat_id?: string;
  source_message_id?: string;
  status: PendingMemoryStatus;
  created_at: string;
  resolved_at?: string;
  is_conflict?: boolean;
  conflict_old_memory_id?: string;
  conflict_old_content?: string;
  conflict_accuracy_score?: number;
  conflict_importance?: number;
  conflict_auto_resolve_at?: string;
}

export interface Memory {
  id: string;
  memory_type: MemoryType;
  content: string;
  importance?: number;
  confidence?: number;
  status: MemoryStatusType;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
  projected_category?: string;
  projected_label?: string;
  influence_explanation?: string;
  key?: string;
  value?: string;
  trigger?: string;
  action?: string;
  reasoning?: string;
  application?: string;
  tool_name?: string;
  tool_rule_priority?: 'critical' | 'high' | 'normal';
  is_user_locked?: boolean;
  event_type?: string;
  related_entities?: string[];
  tags?: string[];
  last_accessed_at?: string;
  access_count?: number;
  correction_of?: string;
  source_error?: string;
  source_chat_id?: string;
  source_message_id?: string;
}

export interface MemoryPaginationInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PendingMemoryListResponse {
  items: PendingMemory[];
  total: number;
}

export interface MemoryListResponse {
  items: Memory[];
  pagination: MemoryPaginationInfo;
}

export interface ApproveMemoryRequest {
  edited_content?: string;
}

export interface BatchMemoryRequest {
  memory_ids: string[];
}

export interface BatchMemoryResponse {
  success_count: number;
  failed_count: number;
  failed_ids?: string[];
}

export interface UpdateMemoryRequest {
  content?: string;
  reasoning?: string;
  application?: string;
  importance?: number;
  tags?: string[];
}

export interface MemorySearchResponse {
  results: Memory[];
  scores: number[];
  query: string;
  total: number;
}

export interface MemoryStatsResponse {
  total_memories: number;
  by_type: Record<MemoryType, number>;
}

export interface TagStatsItem {
  tag: string;
  count: number;
}

export interface TagStatsResponse {
  tags: TagStatsItem[];
  total_tagged: number;
}

export interface CreateMemoryRequest {
  memory_type: MemoryType;
  content: string;
  importance?: number;
  tags?: string[];
  key?: string;
  value?: string;
  trigger?: string;
  action?: string;
  related_entities?: string[];
}

// ==================== API 函数 ====================

export const createMemory = async (body: CreateMemoryRequest): Promise<Memory> => {
  return apiRequest<Memory>('/memory/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const getPendingMemories = async (userId?: string): Promise<PendingMemoryListResponse> => {
  const params = new URLSearchParams();
  if (userId) params.append('user_id', userId);
  const qs = params.toString();
  return apiRequest<PendingMemoryListResponse>(`/memory/pending${qs ? `?${qs}` : ''}`);
};

export const approveMemory = async (memoryId: string, editedContent?: string): Promise<void> => {
  const body: ApproveMemoryRequest = {};
  if (editedContent) body.edited_content = editedContent;
  await apiRequest(`/memory/pending/${memoryId}/approve`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const rejectMemory = async (memoryId: string): Promise<void> => {
  await apiRequest(`/memory/pending/${memoryId}/reject`, { method: 'POST' });
};

export const batchApproveMemories = async (memoryIds: string[]): Promise<BatchMemoryResponse> => {
  return apiRequest<BatchMemoryResponse>('/memory/pending/batch/approve', {
    method: 'POST',
    body: JSON.stringify({ memory_ids: memoryIds }),
  });
};

export const batchRejectMemories = async (memoryIds: string[]): Promise<BatchMemoryResponse> => {
  return apiRequest<BatchMemoryResponse>('/memory/pending/batch/reject', {
    method: 'POST',
    body: JSON.stringify({ memory_ids: memoryIds }),
  });
};

export const getConflicts = async (): Promise<PendingMemoryListResponse> => {
  return apiRequest<PendingMemoryListResponse>('/memory/conflicts');
};

export const resolveConflict = async (
  conflictId: string,
  resolution: ConflictResolution,
  mergedContent?: string,
): Promise<void> => {
  await apiRequest(`/memory/conflicts/${conflictId}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ resolution, merged_content: mergedContent }),
  });
};

export type MemorySortBy = 'created_at' | 'updated_at' | 'importance';
export type MemorySortOrder = 'asc' | 'desc';

export const getMemories = async (
  params: {
    type?: MemoryType;
    page?: number;
    pageSize?: number;
    search?: string;
    tag?: string;
    sortBy?: MemorySortBy;
    sortOrder?: MemorySortOrder;
  } = {},
): Promise<MemoryListResponse> => {
  const searchParams = new URLSearchParams();
  if (params.type) searchParams.append('type', params.type);
  if (params.page) searchParams.append('page', params.page.toString());
  if (params.pageSize) searchParams.append('page_size', params.pageSize.toString());
  if (params.search) searchParams.append('search', params.search);
  if (params.tag) searchParams.append('tag', params.tag);
  if (params.sortBy) searchParams.append('sort_by', params.sortBy);
  if (params.sortOrder) searchParams.append('sort_order', params.sortOrder);
  const qs = searchParams.toString();
  return apiRequest<MemoryListResponse>(`/memory/${qs ? `?${qs}` : ''}`);
};

export const updateMemory = async (
  memoryType: MemoryType,
  memoryId: string,
  updates: UpdateMemoryRequest,
): Promise<Memory> => {
  return apiRequest<Memory>(`/memory/${memoryType}/${memoryId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
};

export const deleteMemory = async (memoryId: string, memoryType: MemoryType): Promise<void> => {
  await apiRequest(`/memory/${memoryId}?memory_type=${memoryType}`, {
    method: 'DELETE',
  });
};

export const deleteAllMemories = async (memoryType?: MemoryType): Promise<{ deleted_count: number }> => {
  const qs = memoryType ? `?memory_type=${memoryType}` : '';
  return apiRequest(`/memory/all${qs}`, { method: 'DELETE' });
};

export const searchMemories = async (
  query: string,
  params: { memoryTypes?: MemoryType[]; limit?: number } = {},
): Promise<MemorySearchResponse> => {
  const searchParams = new URLSearchParams({ query });
  if (params.memoryTypes?.length) {
    searchParams.append('memory_types', params.memoryTypes.join(','));
  }
  if (params.limit) searchParams.append('limit', params.limit.toString());
  return apiRequest<MemorySearchResponse>(`/memory/search?${searchParams}`);
};

export const getMemoryStats = async (): Promise<MemoryStatsResponse> => {
  return apiRequest<MemoryStatsResponse>('/memory/stats');
};

export const getMemoryTags = async (limit = 20): Promise<TagStatsResponse> => {
  return apiRequest<TagStatsResponse>(`/memory/tags?limit=${limit}`);
};

export const getMemoryContext = async (): Promise<Record<string, unknown>> => {
  return apiRequest<Record<string, unknown>>('/memory/context');
};

// ==================== 导出 ====================

export interface MemoryExportResponse {
  version: number;
  data: Record<string, Record<string, unknown>[]>;
  total_count: number;
}

export const exportMemories = async (): Promise<MemoryExportResponse> => {
  return apiRequest<MemoryExportResponse>('/memory/export');
};

export const exportMemoriesMarkdown = async (agentId?: string): Promise<void> => {
  const params = new URLSearchParams();
  if (agentId) params.append('agent_id', agentId);
  const qs = params.toString();
  const response = await fetch(`/api/v1/memory/export/markdown${qs ? `?${qs}` : ''}`, {
    credentials: 'include',
  });
  if (!response.ok) throw new Error('Export markdown failed');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const disposition = response.headers.get('Content-Disposition');
  a.download = disposition?.match(/filename="(.+)"/)?.[1] ?? 'memories_markdown.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

export interface SafeRulePreviewItem {
  id: string;
  content: string;
  rendered: string;
}

export const previewRulesSafe = async (params: {
  agentId?: string;
  ruleIds?: string[];
  format?: 'markdown' | 'json';
}): Promise<SafeRulePreviewItem[]> => {
  const qs = new URLSearchParams();
  if (params.agentId) qs.append('agent_id', params.agentId);
  if (params.ruleIds?.length) qs.append('rule_ids', params.ruleIds.join(','));
  if (params.format) qs.append('output_format', params.format);
  return apiRequest<SafeRulePreviewItem[]>(`/memory/export/rules-safe/preview?${qs.toString()}`);
};

export const exportRulesSafe = async (params: {
  agentId?: string;
  ruleIds?: string[];
  format?: 'markdown' | 'json';
}): Promise<void> => {
  const qs = new URLSearchParams();
  if (params.agentId) qs.append('agent_id', params.agentId);
  if (params.ruleIds?.length) qs.append('rule_ids', params.ruleIds.join(','));
  if (params.format) qs.append('output_format', params.format ?? 'markdown');
  const response = await fetch(`/api/v1/memory/export/rules-safe?${qs.toString()}`, {
    credentials: 'include',
  });
  if (!response.ok) throw new Error('Export rules failed');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const disposition = response.headers.get('Content-Disposition');
  a.download = disposition?.match(/filename="(.+)"/)?.[1] ?? 'rules_safe.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

export interface RateMemoryResponse {
  success: boolean;
  memory_id: string;
  score: number;
}

export const rateMemory = async (memoryId: string, score: number): Promise<RateMemoryResponse> => {
  return apiRequest<RateMemoryResponse>(`/memory/${memoryId}/rate`, {
    method: 'POST',
    body: JSON.stringify({ score }),
  });
};

export interface TasteSummaryResponse {
  style_keywords: string[];
  preference_keywords: string[];
  avoid_keywords: string[];
  current_goals?: string[];
  reply_style?: string;
  technical_depth?: string;
  proactivity?: string;
  summary: string;
  memory_count: number;
}

export const getTasteSummary = async (): Promise<TasteSummaryResponse> => {
  return apiRequest<TasteSummaryResponse>('/memory/taste-summary');
};

export const updateMemoryStatus = async (memoryId: string, status: MemoryStatusType): Promise<Memory> => {
  return apiRequest<Memory>(`/memory/${memoryId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
};

// ==================== Memory Guardian ====================

export interface MemoryHealthScore {
  total: number;
  dimensions: Record<string, number>;
  suggestions: string[];
  has_graph: boolean;
}

export type MemoryGuardianFrequencyTier = 'conservative' | 'balanced' | 'aggressive';
export type MemoryGuardianTriggerMode = 'safe' | 'force';

export interface MemoryGuardianPolicy {
  frequency_tier: MemoryGuardianFrequencyTier;
  quiet_window_enabled: boolean;
  quiet_window_start_hour: number;
  quiet_window_end_hour: number;
  timezone_offset_minutes: number;
  timezone_initialized?: boolean;
  timezone_source?: 'unknown' | 'client_header' | 'server_fallback' | 'manual';
}

export interface MemoryGuardianStatus {
  running: boolean;
  last_run: number | null;
  next_run: number | null;
  healthy_interval_hours: number;
  unhealthy_interval_hours: number;
  health_threshold: number;
  seconds_until_next: number | null;
  frequency_tier: MemoryGuardianFrequencyTier;
  quiet_window_enabled: boolean;
  quiet_window_start_hour: number;
  quiet_window_end_hour: number;
  timezone_offset_minutes: number;
  local_hour: number;
  within_quiet_window: boolean;
  seconds_until_quiet_window: number;
}

export interface MemoryHealthResponse {
  health: MemoryHealthScore;
  guardian: MemoryGuardianStatus;
  policy: MemoryGuardianPolicy;
  alerts?: {
    guard_unavailable?: {
      active: boolean;
      escalated: boolean;
      window_hours: number;
      total: number;
      reasons: Record<string, number>;
      dominant_reason: string | null;
      dominant_reason_count: number;
      dominant_reason_ratio: number;
      thresholds?: {
        min_total_events: number;
        escalation_min_reason_count: number;
        escalation_min_reason_ratio: number;
      } | null;
      last_occurred_at: string | null;
    };
  };
}

export interface MemoryMaintenanceTriggerResponse {
  triggered: boolean;
  mode: MemoryGuardianTriggerMode;
  applied: boolean;
  skipped_reason?: string;
  health?: MemoryHealthScore;
  error?: string;
}

export const getMemoryHealth = async (): Promise<MemoryHealthResponse> => {
  const timezoneOffsetMinutes = typeof window !== 'undefined' ? -new Date().getTimezoneOffset() : 0;
  return apiRequest<MemoryHealthResponse>('/memory/guardian/health', {
    headers: { 'x-client-timezone-offset-minutes': String(timezoneOffsetMinutes) },
  });
};

export const triggerMemoryMaintenance = async (
  mode: MemoryGuardianTriggerMode = 'safe',
): Promise<MemoryMaintenanceTriggerResponse> => {
  return apiRequest<MemoryMaintenanceTriggerResponse>('/memory/guardian/trigger', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
};

export const getMemoryGuardianPolicy = async (): Promise<MemoryGuardianPolicy> => {
  return apiRequest<MemoryGuardianPolicy>('/memory/guardian/policy', { silent: true });
};

export const updateMemoryGuardianPolicy = async (
  policy: MemoryGuardianPolicy,
): Promise<MemoryGuardianPolicy> => {
  return apiRequest<MemoryGuardianPolicy>('/memory/guardian/policy', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  });
};

export interface MemoryGuardianMorningDigest {
  available: boolean;
  occurred_at?: string;
  summary?: string;
  counts?: {
    forgotten: number;
    archived: number;
    merged: number;
    corrected: number;
    stale_removed: number;
    stale_extended: number;
  };
  forced?: boolean;
  forced_runs?: number;
  scheduled_runs?: number;
  event_count?: number;
  duration_ms?: number;
  health_total?: number;
  health_delta?: number | null;
  health_status?: string | null;
  next_run_seconds?: number | null;
  window_started_at?: string;
  window_ended_at?: string;
  window_mode?: 'quiet_window' | 'rolling_24h';
}

export interface MemoryGuardianOverviewResponse extends MemoryHealthResponse {
  digest: MemoryGuardianMorningDigest;
}

export const getMemoryGuardianOverview = async (): Promise<MemoryGuardianOverviewResponse> => {
  const timezoneOffsetMinutes = typeof window !== 'undefined' ? -new Date().getTimezoneOffset() : 0;
  return apiRequest<MemoryGuardianOverviewResponse>('/memory/guardian/overview', {
    silent: true,
    headers: { 'x-client-timezone-offset-minutes': String(timezoneOffsetMinutes) },
  });
};

export const getMemoryGuardianMorningDigest = async (): Promise<MemoryGuardianMorningDigest> => {
  const timezoneOffsetMinutes = typeof window !== 'undefined' ? -new Date().getTimezoneOffset() : 0;
  return apiRequest<MemoryGuardianMorningDigest>('/memory/guardian/morning-digest', {
    silent: true,
    headers: { 'x-client-timezone-offset-minutes': String(timezoneOffsetMinutes) },
  });
};

// ==================== Trash (Soft Delete) ====================

export const getArchivedMemories = async (
  params: { type?: MemoryType; page?: number; pageSize?: number } = {},
): Promise<MemoryListResponse> => {
  const searchParams = new URLSearchParams();
  if (params.type) searchParams.append('type', params.type);
  if (params.page) searchParams.append('page', params.page.toString());
  if (params.pageSize) searchParams.append('page_size', params.pageSize.toString());
  const qs = searchParams.toString();
  return apiRequest<MemoryListResponse>(`/memory/trash${qs ? `?${qs}` : ''}`);
};

export const restoreMemory = async (memoryId: string): Promise<Memory> => {
  return apiRequest<Memory>(`/memory/trash/${memoryId}/restore`, {
    method: 'POST',
  });
};

export const purgeMemory = async (memoryId: string): Promise<void> => {
  await apiRequest(`/memory/trash/${memoryId}/purge`, {
    method: 'DELETE',
  });
};

// ==================== Working State ====================

export interface WorkingStateResponse {
  content: string | null;
  updated_at: string | null;
  ttl_days: number;
  expired: boolean;
}

export const getWorkingState = async (): Promise<WorkingStateResponse> => {
  return apiRequest<WorkingStateResponse>('/memory/working-state');
};

export const updateWorkingState = async (content: string): Promise<WorkingStateResponse> => {
  return apiRequest<WorkingStateResponse>('/memory/working-state', {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
};

export const clearWorkingState = async (): Promise<WorkingStateResponse> => {
  return apiRequest<WorkingStateResponse>('/memory/working-state', {
    method: 'DELETE',
  });
};
