/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TreeNode } from '@/services/wikiService';
import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import { apiRequest, resetKit, service, toast } from './wikiSectionTestKit';
import { compileRunOf, healthOf, richStats, statsOf } from './wikiSectionFixtures';
import { useWikiOverviewData } from '../useWikiOverviewData';

interface BridgeHandlers {
  applyStats: (stats: unknown) => void;
  applyHealth: (health: unknown) => void;
}

const WARM_KEY = 'e2e_warm_platform_readiness';
const NODE: TreeNode = { id: 'raw', name: 'raw', is_dir: true, children: [] };
const registerHandlers = vi.fn();
const unregisterHandlers = vi.fn();
const fetchMock = vi.fn();
let consoleWarn: ReturnType<typeof vi.spyOn>;
let consoleError: ReturnType<typeof vi.spyOn>;

const setup = async (scope: string | null = null) => {
  const rendered = renderHook(() => useWikiOverviewData(scope, 'overview'));
  await settle();
  return rendered;
};

const handlers = (): BridgeHandlers => registerHandlers.mock.calls[0][0];

const jsonResponse = (body: unknown, ok = true) => ({ ok, json: async () => body });

/** Answers the page's own fetches: stats and health report by path, everything else is a 404. */
function serveFetch(routes: { stats?: () => unknown; health?: () => unknown }) {
  fetchMock.mockImplementation(async (url: string) => {
    const route = url.includes('/wiki/stats')
      ? routes.stats
      : url.includes('/wiki/health-report')
        ? routes.health
        : undefined;
    return route ? route() : jsonResponse({}, false);
  });
}

beforeEach(() => {
  resetKit();
  registerHandlers.mockClear();
  unregisterHandlers.mockClear();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  Reflect.deleteProperty(window, '__MYRM_E2E_WIKI__');
  consoleWarn.mockRestore();
  consoleError.mockRestore();
});

describe('useWikiOverviewData: E2E bridge on a local host', () => {
  beforeEach(() => {
    Object.assign(window, { __MYRM_E2E_WIKI__: { registerHandlers, unregisterHandlers } });
  });

  it('registers handlers that inject stats, ending a pending load, and unregisters them when the page goes away', async () => {
    apiRequest.mockReturnValue(deferred<ReturnType<typeof statsOf>>().promise);
    const { result, unmount } = await setup();
    expect(registerHandlers).toHaveBeenCalledOnce();
    expect(result.current.stats).toBeNull();
    expect(result.current.isLoadingStats).toBe(true);

    act(() => handlers().applyStats(richStats()));
    expect(result.current.stats).toEqual(richStats());
    expect(result.current.isLoadingStats).toBe(false);

    unmount();
    expect(unregisterHandlers).toHaveBeenCalledOnce();
  });

  it('registers handlers that inject a health report, open it and clear a load error', async () => {
    service.getHealthReport.mockRejectedValue(new Error('no report'));
    const { result } = await setup();
    expect(result.current.healthReportLoadError).toBe(true);

    const report = healthOf({ open_actions_count: 0, issues_found: 3 });
    act(() => handlers().applyHealth(report));
    expect(result.current.healthReport).toEqual(report);
    expect(result.current.healthReportExpanded).toBe(true);
    expect(result.current.healthReportLoadError).toBe(false);
    expect(result.current.isLoadingHealthReport).toBe(false);
  });

  it('ends a pending health report load when the bridge delivers the report', async () => {
    service.getHealthReport.mockReturnValue(deferred<ReturnType<typeof healthOf>>().promise);
    const { result } = await setup();
    expect(result.current.isLoadingHealthReport).toBe(true);
    act(() => handlers().applyHealth(healthOf()));
    expect(result.current.isLoadingHealthReport).toBe(false);
  });

  it('works without an E2E bridge on the page', async () => {
    Reflect.deleteProperty(window, '__MYRM_E2E_WIKI__');
    const { result } = await setup();
    expect(result.current.stats).toEqual(statsOf());
    expect(registerHandlers).not.toHaveBeenCalled();
  });

  it('takes stats from a test event, then asks for the health report of that scope', async () => {
    const { result } = await setup('a1');
    service.getHealthReport.mockClear();
    await act(async () => {
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-stats', { detail: statsOf({ total_concepts: 99 }) }));
    });
    await settle();
    expect(result.current.stats?.total_concepts).toBe(99);
    expect(service.getHealthReport).toHaveBeenCalledExactlyOnceWith('a1');
  });

  it('asks for the health report of the scope the page is in now, not the one it opened with', async () => {
    const { rerender } = renderHook(({ scope }) => useWikiOverviewData(scope, 'overview'), {
      initialProps: { scope: 'a1' },
    });
    await settle();
    rerender({ scope: 'a2' });
    await settle();
    service.getHealthReport.mockClear();
    await act(async () => {
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-stats', { detail: statsOf() }));
    });
    await settle();
    expect(service.getHealthReport).toHaveBeenCalledExactlyOnceWith('a2');
  });

  it('takes a health report from a test event and opens it', async () => {
    const { result } = await setup();
    const report = healthOf({ issues_found: 7 });
    await act(async () => {
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-health-report', { detail: report }));
    });
    expect(result.current.healthReport).toEqual(report);
    expect(result.current.healthReportExpanded).toBe(true);
  });

  it.each([null, 'text', 3])('ignores a test event without a usable payload (%j)', async (detail) => {
    const { result } = await setup();
    const before = result.current.stats;
    service.getHealthReport.mockClear();
    await act(async () => {
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-stats', { detail }));
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-health-report', { detail }));
    });
    expect(result.current.stats).toBe(before);
    expect(result.current.healthReport).toEqual(healthOf());
    expect(service.getHealthReport).not.toHaveBeenCalled();
  });

  it('stops listening for both test events when the page goes away', async () => {
    const added = vi.spyOn(window, 'addEventListener');
    const removed = vi.spyOn(window, 'removeEventListener');
    try {
      const { unmount } = await setup();
      unmount();
      for (const event of ['myrm-e2e-wiki-stats', 'myrm-e2e-wiki-health-report']) {
        const listener = added.mock.calls.find(([type]) => type === event)?.[1];
        expect(listener).toBeTypeOf('function');
        expect(removed).toHaveBeenCalledWith(event, listener);
      }
    } finally {
      added.mockRestore();
      removed.mockRestore();
    }
  });
});

describe('useWikiOverviewData: warm-platform fetch fallback', () => {
  beforeEach(() => {
    sessionStorage.setItem(WARM_KEY, 'true');
  });

  it('never uses fetch unless the platform marked itself warm', async () => {
    sessionStorage.removeItem(WARM_KEY);
    await setup();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reads the stats with fetch first, unwrapping a data envelope, and skips the API client', async () => {
    serveFetch({
      stats: () => jsonResponse({ data: richStats() }),
      health: () => jsonResponse(healthOf({ open_actions_count: 2 })),
    });
    service.getRawTree.mockResolvedValue([NODE]);
    service.getQueueStatus.mockResolvedValue({
      stats: {},
      pending_items: [],
      failed_items: [],
      compile_run: compileRunOf(),
    });
    const { result } = await setup('a1');
    expect(fetchMock).toHaveBeenCalledWith('/wiki/stats?agent_id=a1', { cache: 'no-store' });
    expect(fetchMock).toHaveBeenCalledWith('/wiki/health-report?agent_id=a1', { cache: 'no-store' });
    expect(result.current.rawTreeData).toEqual([NODE]);
    expect(result.current.compileRun).toEqual(compileRunOf());
    expect(result.current.stats).toEqual(richStats());
    expect(apiRequest).not.toHaveBeenCalled();
    expect(result.current.isLoadingStats).toBe(false);
    expect(service.getRawTree).toHaveBeenCalledExactlyOnceWith('a1');
    expect(service.getQueueStatus).toHaveBeenCalledExactlyOnceWith('a1');
  });

  it('accepts stats and health reports that come without an envelope', async () => {
    serveFetch({
      stats: () => jsonResponse(statsOf({ total_concepts: 55 })),
      health: () => jsonResponse(healthOf({ issues_found: 4 })),
    });
    const { result } = await setup();
    expect(result.current.stats?.total_concepts).toBe(55);
    expect(fetchMock).toHaveBeenCalledWith('/wiki/health-report', { cache: 'no-store' });
    expect(result.current.healthReport?.issues_found).toBe(4);
    expect(service.getHealthReport).not.toHaveBeenCalled();
    expect(result.current.healthReportExpanded).toBe(false);
    expect(result.current.isLoadingHealthReport).toBe(false);
  });

  it('opens a fetched health report that has open actions', async () => {
    serveFetch({
      stats: () => jsonResponse(statsOf()),
      health: () => jsonResponse({ data: healthOf({ open_actions_count: 1 }) }),
    });
    const { result } = await setup();
    expect(result.current.healthReportExpanded).toBe(true);
  });

  it('goes on to the API when fetch has no usable answer', async () => {
    serveFetch({});
    const { result } = await setup();
    expect(apiRequest).toHaveBeenCalledWith('/wiki/stats');
    expect(service.getHealthReport).toHaveBeenCalledOnce();
    expect(result.current.stats).toEqual(statsOf());
  });

  it('retries with fetch after the API fails, so the failure toast never shows', async () => {
    let statsCalls = 0;
    let healthCalls = 0;
    serveFetch({
      stats: () => jsonResponse(++statsCalls === 1 ? {} : richStats(), statsCalls > 1),
      health: () => jsonResponse(++healthCalls === 1 ? {} : healthOf({ issues_found: 6 }), healthCalls > 1),
    });
    apiRequest.mockRejectedValue(new Error('api down'));
    service.getHealthReport.mockRejectedValue(new Error('api down'));
    const { result } = await setup();
    expect(result.current.stats).toEqual(richStats());
    expect(toast.error).not.toHaveBeenCalled();
    expect(result.current.healthReport?.issues_found).toBe(6);
    expect(result.current.healthReportLoadError).toBe(false);
    expect(result.current.isLoadingStats).toBe(false);
    expect(result.current.isLoadingRawTree).toBe(false);
    expect(consoleError).toHaveBeenCalledWith('Failed to load Wiki stats:', expect.any(Error));
  });

  it('keeps the fetched stats, logs why and stops the tree spinner when the trees cannot be loaded', async () => {
    const failure = new Error('tree down');
    serveFetch({ stats: () => jsonResponse(richStats()), health: () => jsonResponse(healthOf()) });
    service.getRawTree.mockRejectedValue(failure);
    const { result } = await setup();
    expect(result.current.stats).toEqual(richStats());
    expect(consoleWarn).toHaveBeenCalledWith('Failed to load wiki ingest trees:', failure);
    expect(result.current.isLoadingRawTree).toBe(false);
  });

  it('warns and falls through to the API when fetch itself throws', async () => {
    const failure = new Error('network');
    fetchMock.mockRejectedValue(failure);
    const { result } = await setup();
    expect(consoleWarn).toHaveBeenCalledWith('Wiki stats E2E fallback failed:', failure);
    expect(consoleWarn).toHaveBeenCalledWith('Wiki health report E2E fallback failed:', failure);
    expect(result.current.stats).toEqual(statsOf());
    expect(service.getHealthReport).toHaveBeenCalledOnce();
    expect(result.current.healthReport).toEqual(healthOf());
  });
});
