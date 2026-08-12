/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCasesEval } from '../hooks/useCasesEval';

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
}

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function installFetchMock(routes: Record<string, unknown>) {
  const keys = Object.keys(routes).sort((a, b) => b.length - a.length);
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    const match = keys.find((key) => url.includes(key));
    if (!match) {
      return jsonResponse({ status: 'error' });
    }
    return jsonResponse(routes[match]);
  });
}

const defaultRoutes = {
  '/api/v1/eval/status': { is_running: false, total: 0, completed: 0 },
  '/api/v1/eval/reports/latest': { status: 'success', summary: null },
  '/api/v1/eval/reports': { status: 'success', reports: [] },
  '/api/v1/eval/datasets/default': { status: 'success', content: '[]' },
};

describe('useCasesEval', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    MockEventSource.instances = [];
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
  });

  it('starts a single-profile run with the expected payload', async () => {
    const fetchMock = installFetchMock({
      ...defaultRoutes,
      '/api/v1/eval/run': { status: 'started' },
    });
    const onStarted = vi.fn();

    const { result } = renderHook(() => useCasesEval('default'));
    await act(async () => {
      await result.current.startRun('agent-1', 'default', false, onStarted);
    });

    const runCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(runCall).toBeDefined();
    const body = JSON.parse(String((runCall?.[1] as RequestInit).body));
    expect(body).toEqual({ profile_id: 'agent-1', dataset_id: 'default', benchmark_mode: false });
    expect(result.current.running).toBe(true);
    expect(onStarted).toHaveBeenCalledTimes(1);
  });

  it('starts a benchmark run with a sample limit', async () => {
    const fetchMock = installFetchMock({
      ...defaultRoutes,
      '/api/v1/eval/benchmarks/run': { status: 'started' },
    });

    const { result } = renderHook(() => useCasesEval('default'));
    await act(async () => {
      await result.current.startBenchmark('wb-bench-office', 'agent-1', true, 20);
    });

    const runCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    const body = JSON.parse(String((runCall?.[1] as RequestInit).body));
    expect(body).toEqual({
      benchmark_id: 'wb-bench-office',
      profile_id: 'agent-1',
      benchmark_mode: true,
      limit: 20,
    });
    expect(result.current.running).toBe(true);
  });

  it('aborts against the single-eval abort endpoint', async () => {
    installFetchMock({
      ...defaultRoutes,
      '/api/v1/eval/abort': { ok: true },
    });

    const { result } = renderHook(() => useCasesEval('default'));
    await act(async () => {
      await result.current.abort();
    });

    const abortCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url, init]) => String(url).includes('/api/v1/eval/abort') && (init as RequestInit).method === 'POST',
    );
    expect(abortCall).toBeDefined();
  });

  it('loads a historical report and reports success', async () => {
    installFetchMock({
      ...defaultRoutes,
      '/api/v1/eval/reports/report_1.json': { status: 'success', summary: { total: 3, passed: 2 } },
    });

    const { result } = renderHook(() => useCasesEval('default'));
    let loaded = false;
    await act(async () => {
      loaded = await result.current.loadHistoryReport('report_1.json');
    });

    expect(loaded).toBe(true);
    expect(result.current.report?.total).toBe(3);
    await waitFor(() => expect(result.current.loadingReport).toBeNull());
  });
});
