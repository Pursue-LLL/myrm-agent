import { apiRequest } from '@/lib/api';

export type BackgroundTaskKind = 'agent' | 'shell';

export type BackgroundTaskStatus =
  | 'running'
  | 'completed'
  | 'failed'
  | 'timed_out'
  | 'cancelled';

export interface BackgroundTask {
  kind: BackgroundTaskKind;
  task_id: string;
  prompt: string;
  status: BackgroundTaskStatus;
  created_at: number;
  completed_at: number | null;
  result_preview: string | null;
  chat_id?: string | null;
  pid?: number | null;
  progress_percent?: number | null;
  exit_code?: number | null;
  error_category?: string | null;
}

export interface BackgroundTaskListResponse {
  tasks: BackgroundTask[];
  registry_ephemeral?: boolean;
}

export async function listBackgroundTasks(): Promise<BackgroundTaskListResponse> {
  return apiRequest<BackgroundTaskListResponse>('/background-tasks');
}

export async function getBackgroundTask(taskId: string): Promise<BackgroundTask> {
  return apiRequest<BackgroundTask>(`/background-tasks/${encodeURIComponent(taskId)}`);
}

export async function cancelBackgroundTask(taskId: string): Promise<{ message: string; task_id: string }> {
  return apiRequest(`/background-tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
}

export async function steerBackgroundTask(
  taskId: string,
  instruction: string,
): Promise<{ message: string; task_id: string }> {
  return apiRequest(`/background-tasks/${encodeURIComponent(taskId)}/steer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  });
}
