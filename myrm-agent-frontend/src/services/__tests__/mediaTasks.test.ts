import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  ACTIVE_MEDIA_STATUSES,
  MEDIA_TASK_TYPES,
  getMediaTaskChatId,
  getMediaTaskPrompt,
  isActiveMediaStatus,
  isMediaTaskType,
  listActiveMediaTasks,
  listRecentTerminalMediaTasks,
  RECENT_TERMINAL_MEDIA_LIMIT,
} from '@/services/mediaTasks';
import type { Task } from '@/store/tasks/types';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';

const mockApiRequest = vi.mocked(apiRequest);

function createTask(
  taskId: string,
  taskType: string,
  status: Task['status'],
  overrides: Partial<Task> = {},
): Task {
  return {
    task_id: taskId,
    task_type: taskType,
    status,
    payload: { prompt: 'A sunset over mountains', chat_id: 'chat-1' },
    priority: 5,
    progress: status === 'running' ? 42 : 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:01Z',
    ...overrides,
  };
}

describe('mediaTasks', () => {
  beforeEach(() => {
    mockApiRequest.mockReset();
  });

  it('identifies media task types and active statuses', () => {
    expect(isMediaTaskType('image_generate')).toBe(true);
    expect(isMediaTaskType('video_generate')).toBe(true);
    expect(isMediaTaskType('agent_run')).toBe(false);
    expect(isActiveMediaStatus('running')).toBe(true);
    expect(isActiveMediaStatus('succeeded')).toBe(false);
    expect(ACTIVE_MEDIA_STATUSES).toHaveLength(3);
    expect(MEDIA_TASK_TYPES).toEqual(['image_generate', 'video_generate']);
  });

  it('reads prompt and chat_id from payload', () => {
    expect(getMediaTaskPrompt({ prompt: '  hello  ' })).toBe('hello');
    expect(getMediaTaskPrompt({ prompt: '   ' })).toBe('');
    expect(getMediaTaskChatId({ chat_id: 'abc' })).toBe('abc');
    expect(getMediaTaskChatId({ chat_id: '' })).toBeUndefined();
  });

  it('merges active image and video tasks without duplicates', async () => {
    mockApiRequest.mockImplementation(async (endpoint: string) => {
      const url = endpoint.toString();
      if (url.includes('status=pending')) {
        return {
          tasks: [
            createTask('img-1', 'image_generate', 'pending'),
            createTask('other-1', 'audio_transcribe', 'pending'),
          ],
        };
      }
      if (url.includes('status=queued')) {
        return { tasks: [createTask('vid-1', 'video_generate', 'queued')] };
      }
      if (url.includes('status=running')) {
        return {
          tasks: [
            createTask('img-2', 'image_generate', 'running'),
            createTask('vid-2', 'video_generate', 'running'),
          ],
        };
      }
      return { tasks: [] };
    });

    const tasks = await listActiveMediaTasks();

    expect(tasks.map((task) => task.task_id).sort()).toEqual(['img-1', 'img-2', 'vid-1', 'vid-2']);
    expect(mockApiRequest).toHaveBeenCalledTimes(ACTIVE_MEDIA_STATUSES.length);
  });

  it('lists recent terminal media tasks sorted by updated_at and excludes active ids', async () => {
    mockApiRequest.mockImplementation(async (endpoint: string) => {
      const url = endpoint.toString();
      if (url.includes('status=succeeded')) {
        return {
          tasks: [
            createTask('img-old', 'image_generate', 'succeeded', {
              updated_at: '2026-01-01T00:00:00Z',
            }),
            createTask('vid-1', 'video_generate', 'succeeded', {
              updated_at: '2026-01-02T00:00:00Z',
            }),
          ],
        };
      }
      if (url.includes('status=failed')) {
        return {
          tasks: [
            createTask('img-fail', 'image_generate', 'failed', {
              updated_at: '2026-01-03T00:00:00Z',
              error: { error_type: 'timeout', message: 'Timed out', recoverable: 'transient' },
            }),
            createTask('img-active', 'image_generate', 'failed', {
              updated_at: '2026-01-04T00:00:00Z',
            }),
          ],
        };
      }
      return { tasks: [] };
    });

    const tasks = await listRecentTerminalMediaTasks(new Set(['img-active']));

    expect(tasks.map((task) => task.task_id)).toEqual(['img-fail', 'vid-1', 'img-old']);
    expect(tasks.length).toBeLessThanOrEqual(RECENT_TERMINAL_MEDIA_LIMIT);
  });
});
