import { apiRequest } from '@/lib/api';

export type RunSource = 'cron' | 'kanban' | 'background';
export type RunStatus = 'running' | 'ok' | 'error' | 'skipped' | 'cancelled' | 'timed_out';

export interface UnifiedRun {
  id: string;
  source: RunSource;
  status: RunStatus;
  title: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  summary: string | null;
  output: string | null;
  metadata: Record<string, unknown> | null;
  agent_id: string | null;
  job_id: string | null;
  task_id: string | null;
  has_execution_steps: boolean;
}

export interface UnifiedRunsListResponse {
  items: UnifiedRun[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  degraded: boolean;
  failed_sources: RunSource[];
}

export interface ListRunsParams {
  source?: RunSource;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}

export async function listUnifiedRuns(params: ListRunsParams = {}): Promise<UnifiedRunsListResponse> {
  const searchParams = new URLSearchParams();
  if (params.source) searchParams.set('source', params.source);
  if (params.status) searchParams.set('status', params.status);
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));

  const query = searchParams.toString();
  const endpoint = `/runs${query ? `?${query}` : ''}`;
  return apiRequest<UnifiedRunsListResponse>(endpoint);
}
