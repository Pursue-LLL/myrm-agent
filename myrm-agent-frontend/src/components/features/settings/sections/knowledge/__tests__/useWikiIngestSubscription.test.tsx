/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWikiIngestSubscription, type WikiIngestSnapshot } from '../useWikiIngestSubscription';

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly listeners = new Map<string, Set<EventListener>>();
  closed = false;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    const bucket = this.listeners.get(type) ?? new Set<EventListener>();
    bucket.add(listener);
    this.listeners.set(type, bucket);
  }

  removeEventListener(type: string, listener: EventListener) {
    this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    const event = { data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent<string>;
    this.listeners.get(type)?.forEach((listener) => listener(event as unknown as Event));
  }
}

const SNAPSHOT: WikiIngestSnapshot = { stats: { pending: 1, processing: 0, completed: 4, failed: 0 } };

function openStreams() {
  return FakeEventSource.instances.filter((source) => !source.closed);
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useWikiIngestSubscription', () => {
  it('keeps one stream open while the snapshot callback changes identity on every render', () => {
    const received: WikiIngestSnapshot[] = [];
    const { result } = renderHook(() =>
      useWikiIngestSubscription('agent-1', { onSnapshot: (snapshot) => received.push(snapshot) }),
    );

    for (let i = 0; i < 3; i += 1) {
      act(() => {
        FakeEventSource.instances[0].emit('ingest_snapshot', SNAPSHOT);
      });
    }

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(openStreams()).toHaveLength(1);
    expect(received).toHaveLength(3);
    expect(result.current.snapshot).toEqual(SNAPSHOT);
  });

  it('hands snapshots to the latest callback only', () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ onSnapshot }) => useWikiIngestSubscription(null, { onSnapshot }), {
      initialProps: { onSnapshot: first },
    });

    rerender({ onSnapshot: second });
    act(() => {
      FakeEventSource.instances[0].emit('ingest_snapshot', SNAPSHOT);
    });

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith(SNAPSHOT);
  });

  it('reconnects to the new scope and closes the previous stream', () => {
    const { rerender } = renderHook(({ scope }) => useWikiIngestSubscription(scope), {
      initialProps: { scope: 'agent-1' },
    });

    rerender({ scope: 'agent-2' });

    expect(FakeEventSource.instances.map((source) => source.url)).toEqual([
      '/api/v1/wiki/ingest/stream?agent_id=agent-1',
      '/api/v1/wiki/ingest/stream?agent_id=agent-2',
    ]);
    expect(FakeEventSource.instances[0].closed).toBe(true);
    expect(openStreams()).toHaveLength(1);
  });

  it('opens no stream while disabled and closes it on unmount', () => {
    const { rerender, unmount } = renderHook(({ enabled }) => useWikiIngestSubscription(null, { enabled }), {
      initialProps: { enabled: false },
    });
    expect(FakeEventSource.instances).toHaveLength(0);

    rerender({ enabled: true });
    expect(openStreams()).toHaveLength(1);

    unmount();
    expect(openStreams()).toHaveLength(0);
  });

  it('reports the connection state from the stream', () => {
    const { result } = renderHook(() => useWikiIngestSubscription(null));
    expect(result.current.connected).toBe(false);

    act(() => {
      FakeEventSource.instances[0].emit('open', {});
    });
    expect(result.current.connected).toBe(true);

    act(() => {
      FakeEventSource.instances[0].onerror?.();
    });
    expect(result.current.connected).toBe(false);
  });

  it('ignores payloads that carry no queue stats', () => {
    const onSnapshot = vi.fn();
    const { result } = renderHook(() => useWikiIngestSubscription(null, { onSnapshot }));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    act(() => {
      FakeEventSource.instances[0].emit('ingest_snapshot', { agent_id: 'agent-1' });
      FakeEventSource.instances[0].emit('ingest_snapshot', 'not json');
    });

    expect(onSnapshot).not.toHaveBeenCalled();
    expect(result.current.snapshot).toBeNull();
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });
});
