import { apiRequest } from '@/lib/api';

export type TaskSpaceStatus = 'idle' | 'running' | 'takeover' | 'completed' | 'error';

export interface TaskSpaceInfo {
  space_id: string;
  name: string;
  status: TaskSpaceStatus;
  chat_id: string | null;
  created_at: number;
  last_accessed_at: number;
  idle_seconds: number;
  active_pages: number;
  takeover_active: boolean;
  current_url: string;
  current_title: string;
  metadata: Record<string, unknown>;
}

export interface TaskSpaceSnapshot {
  space_id: string;
  url: string;
  title: string;
  screenshot_jpeg_b64: string;
  takeover_active: boolean;
  timestamp: number;
}

export async function fetchTaskSpaces(): Promise<TaskSpaceInfo[]> {
  try {
    return await apiRequest<TaskSpaceInfo[]>('/api/v1/browser/spaces', {
      method: 'GET',
    });
  } catch {
    return [];
  }
}

export async function createTaskSpace(params: {
  spaceId: string;
  name?: string;
  chatId?: string;
}): Promise<TaskSpaceInfo> {
  return await apiRequest<TaskSpaceInfo>('/api/v1/browser/spaces', {
    method: 'POST',
    body: JSON.stringify({
      space_id: params.spaceId,
      name: params.name,
      chat_id: params.chatId,
    }),
  });
}

export async function closeTaskSpace(spaceId: string): Promise<boolean> {
  try {
    await apiRequest<{ success: boolean }>(`/api/v1/browser/spaces/${encodeURIComponent(spaceId)}`, {
      method: 'DELETE',
    });
    return true;
  } catch {
    return false;
  }
}

export async function toggleTaskSpaceTakeover(spaceId: string, enabled: boolean): Promise<TaskSpaceInfo> {
  return await apiRequest<TaskSpaceInfo>(`/api/v1/browser/spaces/${encodeURIComponent(spaceId)}/takeover`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

export async function fetchTaskSpaceSnapshot(spaceId: string): Promise<TaskSpaceSnapshot | null> {
  try {
    return await apiRequest<TaskSpaceSnapshot>(`/api/v1/browser/spaces/${encodeURIComponent(spaceId)}/snapshot`, {
      method: 'GET',
    });
  } catch {
    return null;
  }
}
