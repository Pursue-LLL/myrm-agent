import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, string>) => {
    if (key === 'taskCompleted') return `${params?.taskType} completed`;
    if (key === 'taskFailed') return `${params?.taskType} failed`;
    if (key === 'taskUnknownError') return 'Unknown error';
    return key;
  },
}));

const mockNotify = vi.fn();
vi.mock('@/services/notification', () => ({
  notificationService: { notify: (...args: unknown[]) => mockNotify(...args) },
}));

type TaskStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

interface MockTask {
  task_id: string;
  task_type: string;
  status: TaskStatus;
  payload: Record<string, unknown>;
  priority: number;
  progress: number;
  created_at: string;
  updated_at: string;
  error?: { error_type: string; message: string; recoverable: 'transient' | 'permanent' };
}

class MockEventSource {
  static OPEN = 1;
  readyState = MockEventSource.OPEN;
  private listeners: Record<string, ((event: { data: string }) => void)[]> = {};

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: { data: string }) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(handler);
  }

  emit(type: string, data: unknown) {
    const handlers = this.listeners[type] || [];
    for (const h of handlers) {
      h({ data: JSON.stringify(data) });
    }
  }

  emitRaw(type: string, rawData: string) {
    const handlers = this.listeners[type] || [];
    for (const h of handlers) {
      h({ data: rawData });
    }
  }

  close = vi.fn();

  static instances: MockEventSource[] = [];
  static reset() {
    MockEventSource.instances = [];
  }
}

Object.defineProperty(global, 'EventSource', {
  value: MockEventSource,
  writable: true,
  configurable: true,
});

const createTask = (
  taskId: string,
  status: TaskStatus,
  overrides: Partial<MockTask> = {},
): MockTask => ({
  task_id: taskId,
  task_type: 'image_generate',
  status,
  payload: {},
  priority: 0,
  progress: status === 'running' ? 50 : status === 'succeeded' ? 100 : 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:01Z',
  ...overrides,
});

describe('useTasksSubscription', () => {
  const taskById = new Map<string, MockTask>();
  let pollTasks: MockTask[] = [];
  const mockFetch = vi.fn<(input: RequestInfo | URL) => Promise<Response>>();

  beforeEach(() => {
    MockEventSource.reset();
    mockNotify.mockClear();
    vi.useFakeTimers();
    taskById.clear();
    pollTasks = [];
    mockFetch.mockReset();
    mockFetch.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/v1/tasks?')) {
        return {
          ok: true,
          json: async () => ({ tasks: pollTasks }),
        } as Response;
      }
      if (url.startsWith('/api/v1/tasks/')) {
        const taskId = decodeURIComponent(url.slice('/api/v1/tasks/'.length));
        const task = taskById.get(taskId);
        return {
          ok: task !== undefined,
          json: async () => task,
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({}),
      } as Response;
    });
    Object.defineProperty(global, 'fetch', {
      value: mockFetch,
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('subscribes to SSE and updates task state', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    taskById.set('task-1', createTask('task-1', 'running', { progress: 50 }));
    const { result } = renderHook(() => useTasksSubscription(['task-1']));

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/v1/tasks/stream');

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { task_id: 'task-1' });
      await Promise.resolve();
      await Promise.resolve();
    });

    const task = result.current.get('task-1');
    expect(task).toBeDefined();
    expect(task?.status).toBe('running');
    expect(task?.progress).toBe(50);
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/tasks/task-1');
  });

  it('sends localized notification on task success', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    taskById.set('task-2', createTask('task-2', 'succeeded', { progress: 100 }));
    renderHook(() => useTasksSubscription(['task-2']));

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { task_id: 'task-2' });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockNotify).toHaveBeenCalledWith('image_generate completed', { body: undefined });
  });

  it('sends localized notification on task failure with error message', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    taskById.set(
      'task-3',
      createTask('task-3', 'failed', {
        error: { error_type: 'timeout', message: 'Request timed out', recoverable: 'transient' },
      }),
    );
    renderHook(() => useTasksSubscription(['task-3']));

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { task_id: 'task-3' });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockNotify).toHaveBeenCalledWith('image_generate failed', { body: 'Request timed out' });
  });

  it('sends unknown error message when error field is missing', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    taskById.set('task-4', createTask('task-4', 'failed'));
    renderHook(() => useTasksSubscription(['task-4']));

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { task_id: 'task-4' });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockNotify).toHaveBeenCalledWith('image_generate failed', { body: 'Unknown error' });
  });

  it('ignores events for non-subscribed task_ids', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    taskById.set('task-other', createTask('task-other', 'succeeded'));
    const { result } = renderHook(() => useTasksSubscription(['task-5']));

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { task_id: 'task-other' });
      await Promise.resolve();
    });

    expect(result.current.size).toBe(0);
    expect(mockNotify).not.toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalledWith('/api/v1/tasks/task-other');
  });

  it('syncs subscribed tasks when task_update event payload is malformed', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    pollTasks = [createTask('task-9', 'running', { progress: 65 })];
    const { result } = renderHook(() => useTasksSubscription(['task-9']));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    mockFetch.mockClear();

    await act(async () => {
      MockEventSource.instances[0].emitRaw('task_update', '{not-json');
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/tasks?ids=task-9&detail=true');
    expect(result.current.get('task-9')?.progress).toBe(65);
  });

  it('throttles malformed task_update self-healing sync bursts', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    pollTasks = [createTask('task-10', 'running', { progress: 40 })];
    renderHook(() => useTasksSubscription(['task-10']));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    mockFetch.mockClear();

    await act(async () => {
      MockEventSource.instances[0].emitRaw('task_update', '{bad-1');
      MockEventSource.instances[0].emitRaw('task_update', '{bad-2');
      await Promise.resolve();
      await Promise.resolve();
    });

    const listCalls = mockFetch.mock.calls.filter(([input]) =>
      String(input).startsWith('/api/v1/tasks?ids=task-10&detail=true'),
    );
    expect(listCalls).toHaveLength(1);
  });

  it('syncs subscribed tasks when event requests sync_required', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    pollTasks = [createTask('task-11', 'running', { progress: 33 })];
    const { result } = renderHook(() => useTasksSubscription(['task-11']));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    mockFetch.mockClear();

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { task_id: 'task-other', sync_required: true });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/tasks?ids=task-11&detail=true');
    expect(result.current.get('task-11')?.progress).toBe(33);
    expect(mockFetch).not.toHaveBeenCalledWith('/api/v1/tasks/task-other');
  });

  it('throttles sync_required snapshot sync bursts', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    pollTasks = [createTask('task-12', 'running', { progress: 27 })];
    renderHook(() => useTasksSubscription(['task-12']));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    mockFetch.mockClear();

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { sync_required: true });
      MockEventSource.instances[0].emit('task_update', { sync_required: true });
      await Promise.resolve();
      await Promise.resolve();
    });

    const listCalls = mockFetch.mock.calls.filter(([input]) =>
      String(input).startsWith('/api/v1/tasks?ids=task-12&detail=true'),
    );
    expect(listCalls).toHaveLength(1);
  });

  it('polls with ids+detail when SSE is disconnected', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    pollTasks = [createTask('task-8', 'running', { progress: 80 })];
    const { result } = renderHook(() => useTasksSubscription(['task-8']));
    const source = MockEventSource.instances[0];
    source.readyState = 0;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    const task = result.current.get('task-8');
    expect(task?.progress).toBe(80);
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/tasks?ids=task-8&detail=true');
  });

  it('does not create EventSource when task_ids is empty', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    renderHook(() => useTasksSubscription([]));

    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('closes EventSource on unmount', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    const { unmount } = renderHook(() => useTasksSubscription(['task-6']));

    const source = MockEventSource.instances[0];
    unmount();

    expect(source.close).toHaveBeenCalled();
  });

  it('useTaskSubscription returns single task', async () => {
    const { useTaskSubscription } = await import('../useTasksSubscription');

    taskById.set('task-7', createTask('task-7', 'running', { progress: 75 }));
    const { result } = renderHook(() => useTaskSubscription('task-7'));

    await act(async () => {
      MockEventSource.instances[0].emit('task_update', { task_id: 'task-7' });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current).toBeDefined();
    expect(result.current?.progress).toBe(75);
  });
});
