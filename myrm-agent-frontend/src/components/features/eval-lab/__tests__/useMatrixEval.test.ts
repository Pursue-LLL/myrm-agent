/** @vitest-environment jsdom */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMatrixEval } from '../hooks/useMatrixEval';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
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

describe('useMatrixEval', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    MockEventSource.instances = [];
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
  });

  it('starts a matrix run with the expected payload and flips the running state', async () => {
    const fetchMock = installFetchMock({
      '/api/v1/eval/matrix/reports/latest': { status: 'success', report: null },
      '/api/v1/eval/matrix/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/matrix/run': { status: 'started' },
    });
    const onStarted = vi.fn();

    const { result } = renderHook(() => useMatrixEval());
    await act(async () => {
      await result.current.startMatrix(['agent-1', 'agent-2'], 'default', false, onStarted);
    });

    const runCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(runCall).toBeDefined();
    const body = JSON.parse(String((runCall?.[1] as RequestInit).body));
    expect(body).toEqual({
      profile_ids: ['agent-1', 'agent-2'],
      dataset_id: 'default',
      benchmark_mode: false,
    });
    expect(result.current.matrixRunning).toBe(true);
    expect(onStarted).toHaveBeenCalledTimes(1);
  });

  it('drives matrix progress from SSE messages', async () => {
    installFetchMock({
      '/api/v1/eval/matrix/reports/latest': { status: 'success', report: null },
      '/api/v1/eval/matrix/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/matrix/run': { status: 'started' },
    });

    const { result } = renderHook(() => useMatrixEval());
    await act(async () => {
      await result.current.startMatrix(['agent-1'], 'default', false);
    });

    await act(async () => {
      MockEventSource.emit({
        is_running: true,
        current_profile: 'agent-1',
        stage: 'running',
        profile_progress: 1,
        profile_total: 2,
        case_completed: 3,
        case_total: 10,
      });
    });

    expect(result.current.matrixRunning).toBe(true);
    expect(result.current.matrixProgress).toMatchObject({
      current_profile: 'agent-1',
      stage: 'running',
      profile_progress: 1,
      profile_total: 2,
      case_completed: 3,
      case_total: 10,
    });
  });

  it('aborts the matrix run against the matrix abort endpoint', async () => {
    installFetchMock({
      '/api/v1/eval/matrix/reports/latest': { status: 'success', report: null },
      '/api/v1/eval/matrix/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/matrix/abort': { ok: true },
    });

    const { result } = renderHook(() => useMatrixEval());
    await act(async () => {
      await result.current.abort();
    });

    const abortCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url, init]) => String(url).includes('/api/v1/eval/matrix/abort') && (init as RequestInit).method === 'POST',
    );
    expect(abortCall).toBeDefined();
  });

  it('loads a historical matrix report and updates the selected timestamp', async () => {
    installFetchMock({
      '/api/v1/eval/matrix/reports/latest': { status: 'success', report: null },
      '/api/v1/eval/matrix/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/matrix/reports/1750000000': {
        status: 'success',
        report: { profile_ids: ['agent-1'], total_cases: 2, stable_count: 1, regression_count: 0, stable_rate: 0.5, per_profile: {}, matrix: [], total_ms: 10 },
      },
    });

    const { result } = renderHook(() => useMatrixEval());
    await act(async () => {
      await result.current.loadReport(1750000000);
    });

    expect(result.current.selectedMatrixTs).toBe(1750000000);
    expect(result.current.matrixReport?.total_cases).toBe(2);
  });

  it('re-pulls the report and history when the SSE stream errors out (EOF race)', async () => {
    const report = {
      profile_ids: ['agent-1'],
      total_cases: 1,
      stable_count: 1,
      regression_count: 0,
      stable_rate: 1,
      per_profile: {},
      matrix: [],
      total_ms: 5,
    };
    const fetchMock = installFetchMock({
      '/api/v1/eval/matrix/reports/latest': { status: 'success', report },
      '/api/v1/eval/matrix/reports/history': { status: 'success', reports: [] },
      '/api/v1/eval/matrix/run': { status: 'started' },
    });

    const { result } = renderHook(() => useMatrixEval());
    await act(async () => {
      await result.current.startMatrix(['agent-1'], 'default', false);
    });
    expect(result.current.matrixRunning).toBe(true);

    await act(async () => {
      MockEventSource.instances[0]?.onerror?.();
    });

    expect(result.current.matrixRunning).toBe(false);
    expect(result.current.matrixReport?.total_cases).toBe(1);
    const calls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(calls).toContain('/api/v1/eval/matrix/reports/latest');
    expect(calls).toContain('/api/v1/eval/matrix/reports/history');
  });
});
