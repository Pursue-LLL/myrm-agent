import { apiRequest } from '@/lib/api';

interface TaskAdaptiveContextsResponse {
  data?: {
    digests?: Array<{
      session_id: string;
      task_intent: string | null;
      hotspots: Array<{ file_path: string; read_count: number; write_count: number; last_accessed: number }>;
      anti_patterns: Array<{
        error_signature: string;
        failed_tool: string;
        failed_args: Record<string, unknown>;
        user_correction: string | null;
        timestamp: number;
      }>;
      success_rate: number;
      duration_ms: number;
    }>;
  };
}

export const fetchRecentTaskAdaptiveContexts = async (limit: number = 10): Promise<TaskAdaptiveContextsResponse> => {
  return apiRequest<TaskAdaptiveContextsResponse>(`/agents/task-adaptive/recent?limit=${limit}`);
};
