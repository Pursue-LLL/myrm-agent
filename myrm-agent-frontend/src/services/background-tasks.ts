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
}

export interface BackgroundTaskListResponse {
  tasks: BackgroundTask[];
}

export async function listBackgroundTasks(): Promise<BackgroundTask[]> {
  const res = await apiRequest<BackgroundTaskListResponse>('/background-tasks');
  return res.tasks;
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
