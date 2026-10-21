import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  resetTaskUpdateEventStreamForTests,
  subscribeTaskUpdateEvents,
  isTaskUpdateEventStreamOpen,
} from '@/services/taskEventStream';

class MockEventSource {
  static OPEN = 1;
  static instances: MockEventSource[] = [];
  readyState = MockEventSource.OPEN;
  close = vi.fn();
  private listeners: Record<string, ((event: { data: string }) => void)[]> = {};

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: { data: string }) => void) {
    this.listeners[type] = this.listeners[type] ?? [];
    this.listeners[type].push(handler);
  }

  emit(type: string, data: unknown) {
    for (const handler of this.listeners[type] ?? []) {
      handler({ data: JSON.stringify(data) });
    }
  }

  static reset() {
    MockEventSource.instances = [];
  }
}

Object.defineProperty(global, 'EventSource', {
  value: MockEventSource,
  writable: true,
  configurable: true,
});

describe('taskEventStream', () => {
  beforeEach(() => {
    MockEventSource.reset();
    resetTaskUpdateEventStreamForTests();
  });

  it('shares one EventSource across multiple subscribers', () => {
    const first = vi.fn();
    const second = vi.fn();

    const unsubscribeFirst = subscribeTaskUpdateEvents(first);
    subscribeTaskUpdateEvents(second);

    expect(MockEventSource.instances).toHaveLength(1);

    MockEventSource.instances[0].emit('task_update', {
      task_id: 'img-1',
      status: 'running',
      task_type: 'image_generate',
    });

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);

    unsubscribeFirst();
    expect(MockEventSource.instances[0].close).not.toHaveBeenCalled();
  });

  it('closes EventSource when last subscriber unsubscribes', () => {
    const unsubscribe = subscribeTaskUpdateEvents(vi.fn());
    const source = MockEventSource.instances[0];

    unsubscribe();

    expect(source.close).toHaveBeenCalledTimes(1);
  });

  it('reports open state via isTaskUpdateEventStreamOpen', () => {
    subscribeTaskUpdateEvents(vi.fn());
    const source = MockEventSource.instances[0];

    expect(isTaskUpdateEventStreamOpen()).toBe(true);

    source.readyState = 0;
    expect(isTaskUpdateEventStreamOpen()).toBe(false);
  });
});
