/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: frontend unified REST client)
 * - @/store/tasks/types::Task (POS: async task DTO contract)
 *
 * [OUTPUT]
 * - listActiveMediaTasks / listRecentTerminalMediaTasks / fetchMediaTask / cancelMediaTask
 * - getMediaTaskPrompt / getMediaTaskChatId / isMediaTaskType helpers
 *
 * [POS]
 * REST client for `/api/v1/tasks` media jobs (image_generate, video_generate) consumed by BackgroundTasksPanel.
 */

import { apiRequest } from '@/lib/api';
import type { Task, TaskStatus } from '@/store/tasks/types';

export const MEDIA_TASK_TYPES = ['image_generate', 'video_generate'] as const;

export type MediaTaskType = (typeof MEDIA_TASK_TYPES)[number];

export const ACTIVE_MEDIA_STATUSES: TaskStatus[] = ['pending', 'queued', 'running'];

export const TERMINAL_MEDIA_STATUSES: TaskStatus[] = ['succeeded', 'failed'];

/** Max recent terminal media rows shown in BackgroundTasksPanel. */
export const RECENT_TERMINAL_MEDIA_LIMIT = 10;

const TERMINAL_FETCH_LIMIT = 50;

export function isMediaTaskType(taskType: string): taskType is MediaTaskType {
  return (MEDIA_TASK_TYPES as readonly string[]).includes(taskType);
}

export function isActiveMediaStatus(status: TaskStatus): boolean {
  return ACTIVE_MEDIA_STATUSES.includes(status);
}

export function isTerminalMediaStatus(status: TaskStatus): boolean {
  return TERMINAL_MEDIA_STATUSES.includes(status);
}

export function getMediaTaskPrompt(payload: Record<string, unknown>): string {
  const prompt = payload.prompt;
  return typeof prompt === 'string' && prompt.trim().length > 0 ? prompt.trim() : '';
}

export function getMediaTaskChatId(payload: Record<string, unknown>): string | undefined {
  const chatId = payload.chat_id;
  return typeof chatId === 'string' && chatId.length > 0 ? chatId : undefined;
}

interface TaskListResponse {
  tasks?: Task[];
}

async function listTasksByStatus(status: TaskStatus): Promise<Task[]> {
  return listTasksByStatusWithLimit(status, 100);
}

/** List pending/queued/running image & video generation tasks with payload detail. */
export async function listActiveMediaTasks(): Promise<Task[]> {
  const batches = await Promise.all(ACTIVE_MEDIA_STATUSES.map((status) => listTasksByStatus(status)));
  const byId = new Map<string, Task>();
  for (const batch of batches) {
    for (const task of batch) {
      if (isMediaTaskType(task.task_type) && isActiveMediaStatus(task.status)) {
        byId.set(task.task_id, task);
      }
    }
  }
  return [...byId.values()].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  );
}

/** List recent succeeded/failed image & video tasks for Panel history (excludes active ids). */
export async function listRecentTerminalMediaTasks(excludeTaskIds: ReadonlySet<string> = new Set()): Promise<Task[]> {
  const batches = await Promise.all(
    TERMINAL_MEDIA_STATUSES.map((status) => listTasksByStatusWithLimit(status, TERMINAL_FETCH_LIMIT)),
  );
  const byId = new Map<string, Task>();
  for (const batch of batches) {
    for (const task of batch) {
      if (isMediaTaskType(task.task_type) && isTerminalMediaStatus(task.status) && !excludeTaskIds.has(task.task_id)) {
        byId.set(task.task_id, task);
      }
    }
  }
  return [...byId.values()]
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
    .slice(0, RECENT_TERMINAL_MEDIA_LIMIT);
}

async function listTasksByStatusWithLimit(status: TaskStatus, limit: number): Promise<Task[]> {
  const params = new URLSearchParams({
    status,
    detail: 'true',
    limit: String(limit),
  });
  const data = await apiRequest<TaskListResponse>(`/tasks?${params.toString()}`, { silent: true });
  return Array.isArray(data.tasks) ? data.tasks : [];
}

export async function fetchMediaTask(taskId: string): Promise<Task | null> {
  try {
    return await apiRequest<Task>(`/tasks/${encodeURIComponent(taskId)}`, { silent: true });
  } catch {
    return null;
  }
}

export async function cancelMediaTask(taskId: string): Promise<void> {
  await apiRequest(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
}
