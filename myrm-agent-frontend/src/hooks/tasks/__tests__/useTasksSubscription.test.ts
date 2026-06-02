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

describe('useTasksSubscription', () => {
  beforeEach(() => {
    MockEventSource.reset();
    mockNotify.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('subscribes to SSE and updates task state', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    const { result } = renderHook(() => useTasksSubscription(['task-1']));

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/v1/tasks/stream');

    act(() => {
      MockEventSource.instances[0].emit('task_update', {
        task_id: 'task-1',
        task_type: 'image_generation',
        status: 'running',
        payload: {},
        priority: 0,
        progress: 50,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:01Z',
      });
    });

    const task = result.current.get('task-1');
    expect(task).toBeDefined();
    expect(task?.status).toBe('running');
    expect(task?.progress).toBe(50);
  });

  it('sends localized notification on task success', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    renderHook(() => useTasksSubscription(['task-2']));

    act(() => {
      MockEventSource.instances[0].emit('task_update', {
        task_id: 'task-2',
        task_type: 'image_generation',
        status: 'succeeded',
        payload: {},
        priority: 0,
        progress: 100,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:02Z',
      });
    });

    expect(mockNotify).toHaveBeenCalledWith('image_generation completed', { body: undefined });
  });

  it('sends localized notification on task failure with error message', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    renderHook(() => useTasksSubscription(['task-3']));

    act(() => {
      MockEventSource.instances[0].emit('task_update', {
        task_id: 'task-3',
        task_type: 'image_generation',
        status: 'failed',
        payload: {},
        error: { error_type: 'timeout', message: 'Request timed out', recoverable: 'transient' },
        priority: 0,
        progress: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:03Z',
      });
    });

    expect(mockNotify).toHaveBeenCalledWith('image_generation failed', { body: 'Request timed out' });
  });

  it('sends unknown error message when error field is missing', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    renderHook(() => useTasksSubscription(['task-4']));

    act(() => {
      MockEventSource.instances[0].emit('task_update', {
        task_id: 'task-4',
        task_type: 'image_generation',
        status: 'failed',
        payload: {},
        priority: 0,
        progress: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:04Z',
      });
    });

    expect(mockNotify).toHaveBeenCalledWith('image_generation failed', { body: 'Unknown error' });
  });

  it('ignores events for non-subscribed task_ids', async () => {
    const { useTasksSubscription } = await import('../useTasksSubscription');

    const { result } = renderHook(() => useTasksSubscription(['task-5']));

    act(() => {
      MockEventSource.instances[0].emit('task_update', {
        task_id: 'task-other',
        task_type: 'image_generation',
        status: 'succeeded',
        payload: {},
        priority: 0,
        progress: 100,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:05Z',
      });
    });

    expect(result.current.size).toBe(0);
    expect(mockNotify).not.toHaveBeenCalled();
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

    const { result } = renderHook(() => useTaskSubscription('task-7'));

    act(() => {
      MockEventSource.instances[0].emit('task_update', {
        task_id: 'task-7',
        task_type: 'image_generation',
        status: 'running',
        payload: {},
        priority: 0,
        progress: 75,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:06Z',
      });
    });

    expect(result.current).toBeDefined();
    expect(result.current?.progress).toBe(75);
  });
});
