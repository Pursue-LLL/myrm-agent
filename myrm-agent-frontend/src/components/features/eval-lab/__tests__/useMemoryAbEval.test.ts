/** @vitest-environment jsdom */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMemoryAbEval } from '../hooks/useMemoryAbEval';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  addEventListener = vi.fn();

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  static emit(data: unknown) {
    for (const es of MockEventSource.instances) {
      es.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
    }
  }
}

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function installFetchMock(routes: Record<string, unknown>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    const match = Object.keys(routes).find((key) => url.includes(key));
    if (!match) {
      return jsonResponse({ status: 'error' });
    }
    return jsonResponse(routes[match]);
  });
}

describe('useMemoryAbEval', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    MockEventSource.instances = [];
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
  });

  it('starts a memory A/B run with the expected payload and flips the running state', async () => {
    const fetchMock = installFetchMock({
      '/api/v1/eval/memory-ab/reports/latest': { status: 'success', report: null },
      '/api/v1/eval/memory-ab/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/memory-ab/run': { status: 'started' },
    });
    const onStarted = vi.fn();

    const { result } = renderHook(() => useMemoryAbEval());
    await act(async () => {
      await result.current.start('wb-bench-office', 'agent-1', 20, onStarted);
    });

    const runCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(runCall).toBeDefined();
    const body = JSON.parse(String((runCall?.[1] as RequestInit).body));
    expect(body).toEqual({
      benchmark_id: 'wb-bench-office',
      profile_id: 'agent-1',
      limit: 20,
    });
    expect(result.current.memoryAbRunning).toBe(true);
    expect(onStarted).toHaveBeenCalledTimes(1);
  });

  it('drives memory A/B progress from SSE messages', async () => {
    installFetchMock({
      '/api/v1/eval/memory-ab/reports/latest': { status: 'success', report: null },
      '/api/v1/eval/memory-ab/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/memory-ab/run': { status: 'started' },
    });

    const { result } = renderHook(() => useMemoryAbEval());
    await act(async () => {
      await result.current.start('wb-bench-office', 'agent-1', undefined);
    });

    await act(async () => {
      MockEventSource.emit({
        is_running: true,
        current_arm: 'memory_on',
        stage: 'running',
        profile_progress: 1,
        profile_total: 2,
        case_completed: 4,
        case_total: 8,
      });
    });

    expect(result.current.memoryAbRunning).toBe(true);
    expect(result.current.memoryAbProgress).toMatchObject({
      current_arm: 'memory_on',
      stage: 'running',
      profile_progress: 1,
      profile_total: 2,
      case_completed: 4,
      case_total: 8,
    });
  });

  it('aborts against the memory A/B abort endpoint', async () => {
    installFetchMock({
      '/api/v1/eval/memory-ab/reports/latest': { status: 'success', report: null },
      '/api/v1/eval/memory-ab/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/memory-ab/abort': { ok: true },
    });

    const { result } = renderHook(() => useMemoryAbEval());
    await act(async () => {
      await result.current.abort();
    });

    const abortCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url, init]) => String(url).includes('/api/v1/eval/memory-ab/abort') && (init as RequestInit).method === 'POST',
    );
    expect(abortCall).toBeDefined();
  });
});
