/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import type { TreeNode } from '@/services/wikiService';
import { apiRequest, emitIngest, resetKit, service, toast } from './wikiSectionTestKit';
import { busySnapshot, compileRunOf, healthOf, richStats, snapshotOf, statsOf } from './wikiSectionFixtures';
import { useWikiOverviewData } from '../useWikiOverviewData';

let consoleError: ReturnType<typeof vi.spyOn>;
let consoleWarn: ReturnType<typeof vi.spyOn>;

const NODE: TreeNode = { id: 'raw', name: 'raw', is_dir: true, children: [] };

async function setup(scope: string | null = null, tab = 'overview') {
  const rendered = renderHook(({ scopeId, activeTab }) => useWikiOverviewData(scopeId, activeTab), {
    initialProps: { scopeId: scope, activeTab: tab },
  });
  await settle();
  return rendered;
}

const statsLoads = () => apiRequest.mock.calls.filter(([path]) => String(path).includes('/wiki/stats')).length;

beforeEach(() => {
  resetKit();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  consoleError.mockRestore();
  consoleWarn.mockRestore();
});

describe('useWikiOverviewData: loading the overview', () => {
  it('loads the stats of the scope, then its health report, raw tree and queue', async () => {
    service.getRawTree.mockResolvedValue([NODE]);
    service.getQueueStatus.mockResolvedValue({
      stats: {},
      pending_items: [],
      failed_items: [],
      compile_run: compileRunOf(),
    });
    const { result } = await setup('a1');
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/wiki/stats?agent_id=a1');
    expect(result.current.stats).toEqual(statsOf());
    expect(service.getHealthReport).toHaveBeenCalledExactlyOnceWith('a1');
    expect(service.getRawTree).toHaveBeenCalledExactlyOnceWith('a1');
    expect(service.getQueueStatus).toHaveBeenCalledExactlyOnceWith('a1');
    expect(result.current.rawTreeData).toEqual([NODE]);
    expect(result.current.compileRun).toEqual(compileRunOf());
    expect(result.current.healthReport).toEqual(healthOf());
  });

  it('asks the default wiki when no agent is selected', async () => {
    await setup();
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/wiki/stats');
    expect(service.getRawTree).toHaveBeenCalledExactlyOnceWith(null);
  });

  it('reports the stats and the raw tree as loading until each arrives', async () => {
    const stats = deferred<ReturnType<typeof statsOf>>();
    const tree = deferred<TreeNode[]>();
    apiRequest.mockReturnValue(stats.promise);
    service.getRawTree.mockReturnValue(tree.promise);
    const { result } = renderHook(() => useWikiOverviewData(null, 'overview'));
    expect(result.current.isLoadingStats).toBe(true);
    expect(result.current.isLoadingRawTree).toBe(true);

    stats.resolve(statsOf());
    await settle();
    expect(result.current.isLoadingStats).toBe(false);
    expect(result.current.isLoadingRawTree).toBe(true);

    tree.resolve([]);
    await settle();
    expect(result.current.isLoadingRawTree).toBe(false);
  });

  it('clears a compile run the queue no longer reports', async () => {
    const { result } = await setup();
    expect(result.current.compileRun).toBeNull();
  });

  it('tells the user when the stats cannot be loaded, and still loads the raw tree but no health report', async () => {
    apiRequest.mockRejectedValue(new Error('down'));
    const { result } = await setup();
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.loadStatsFailed');
    expect(result.current.stats).toBeNull();
    expect(result.current.isLoadingStats).toBe(false);
    expect(service.getRawTree).toHaveBeenCalledOnce();
    expect(service.getHealthReport).not.toHaveBeenCalled();
  });

  it('keeps the stats when the raw tree or the queue fail, and logs why', async () => {
    const failure = new Error('tree down');
    service.getRawTree.mockRejectedValue(failure);
    const { result } = await setup();
    expect(result.current.stats).toEqual(statsOf());
    expect(result.current.isLoadingRawTree).toBe(false);
    expect(toast.error).not.toHaveBeenCalled();
    expect(consoleWarn).toHaveBeenCalledWith('Failed to load wiki ingest trees:', failure);
  });

  it('reloads for a new scope but not for a rerender in the same scope', async () => {
    const { rerender } = await setup('a1');
    rerender({ scopeId: 'a1', activeTab: 'overview' });
    await settle();
    expect(statsLoads()).toBe(1);
    rerender({ scopeId: 'a2', activeTab: 'overview' });
    await settle();
    expect(apiRequest).toHaveBeenLastCalledWith('/wiki/stats?agent_id=a2');
    expect(service.getHealthReport).toHaveBeenLastCalledWith('a2');
    expect(statsLoads()).toBe(2);
  });

  it('reloads on demand', async () => {
    const { result } = await setup();
    await act(() => result.current.loadStats());
    expect(statsLoads()).toBe(2);
  });

  it('reloads only when the overview tab is entered again, not on every tab change', async () => {
    const { rerender } = await setup();
    rerender({ scopeId: null, activeTab: 'concepts' });
    await settle();
    rerender({ scopeId: null, activeTab: 'queue' });
    await settle();
    expect(statsLoads()).toBe(1);
    rerender({ scopeId: null, activeTab: 'overview' });
    await settle();
    expect(statsLoads()).toBe(2);
    rerender({ scopeId: null, activeTab: 'overview' });
    await settle();
    expect(statsLoads()).toBe(2);
  });

  it('does not reload when the page opens on another tab and moves between tabs without visiting the overview', async () => {
    const { rerender } = await setup(null, 'queue');
    rerender({ scopeId: null, activeTab: 'concepts' });
    await settle();
    expect(statsLoads()).toBe(1);
  });
});

describe('useWikiOverviewData: the health report', () => {
  it('opens the report when it has open actions and leaves it closed otherwise', async () => {
    service.getHealthReport.mockResolvedValue(healthOf({ open_actions_count: 2 }));
    const { result } = await setup();
    expect(result.current.healthReportExpanded).toBe(true);
    service.getHealthReport.mockResolvedValue(healthOf({ open_actions_count: 0 }));
    act(() => result.current.setHealthReportExpanded(false));
    await act(() => result.current.loadHealthReport());
    expect(result.current.healthReportExpanded).toBe(false);
  });

  it('reports the load while the request is in flight', async () => {
    const pending = deferred<ReturnType<typeof healthOf>>();
    service.getHealthReport.mockReturnValue(pending.promise);
    const { result } = await setup();
    expect(result.current.isLoadingHealthReport).toBe(true);
    pending.resolve(healthOf());
    await settle();
    expect(result.current.isLoadingHealthReport).toBe(false);
  });

  it('flags a failed load, logs the cause and clears the flag on the next success', async () => {
    const failure = new Error('no report');
    service.getHealthReport.mockRejectedValue(failure);
    const { result } = await setup();
    expect(result.current.healthReportLoadError).toBe(true);
    expect(result.current.healthReport).toBeNull();
    expect(result.current.isLoadingHealthReport).toBe(false);
    expect(consoleError).toHaveBeenCalledWith('Failed to load wiki health report:', failure);

    service.getHealthReport.mockResolvedValue(healthOf());
    await act(() => result.current.loadHealthReport());
    expect(result.current.healthReportLoadError).toBe(false);
    expect(result.current.healthReport).toEqual(healthOf());
  });
});

describe('useWikiOverviewData: counts derived from stats and the live queue', () => {
  it('reads the duplicate groups and whether they block the compile from the stats', async () => {
    apiRequest.mockResolvedValue(richStats());
    const { result } = await setup();
    expect(result.current.duplicateGroupsPending).toBe(2);
    expect(result.current.dedupBlocksCompile).toBe(true);
  });

  it('reports no duplicates until the stats say otherwise', async () => {
    const { result } = await setup();
    expect(result.current.duplicateGroupsPending).toBe(0);
    expect(result.current.dedupBlocksCompile).toBe(false);
  });

  it('counts pending synthesis pages from the stats', async () => {
    apiRequest.mockResolvedValue(richStats());
    const { result } = await setup();
    expect(result.current.synthesisPendingCount).toBe(4);
  });

  it('prefers the live count over the stats, even when the live count is zero', async () => {
    apiRequest.mockResolvedValue(richStats());
    const { result } = await setup();
    await emitIngest(snapshotOf({}, { synthesis_pending_count: 9 }));
    expect(result.current.synthesisPendingCount).toBe(9);
    await emitIngest(snapshotOf({}, { synthesis_pending_count: 0 }));
    expect(result.current.synthesisPendingCount).toBe(0);
  });

  it('falls back to the stats when the snapshot carries no count, and to zero without either', async () => {
    apiRequest.mockResolvedValue(richStats());
    const { result } = await setup();
    await emitIngest(snapshotOf());
    expect(result.current.synthesisPendingCount).toBe(4);

    apiRequest.mockRejectedValue(new Error('down'));
    const empty = await setup();
    expect(empty.result.current.synthesisPendingCount).toBe(0);
  });
});

describe('useWikiOverviewData: live queue snapshots', () => {
  it('is not live until the first snapshot', async () => {
    const { result } = await setup();
    expect(result.current.ingestLive).toBe(false);
    expect(result.current.ingestSnapshot).toBeNull();
    await emitIngest(busySnapshot());
    expect(result.current.ingestLive).toBe(true);
    expect(result.current.ingestSnapshot).toEqual(busySnapshot());
  });

  it('follows the compile run the snapshot reports and clears it when the snapshot has none', async () => {
    const { result } = await setup();
    await emitIngest(snapshotOf({}, { compile_run: compileRunOf({ state: 'running', pause_reason: '' }) }));
    expect(result.current.compileRun?.state).toBe('running');
    await emitIngest(snapshotOf());
    expect(result.current.compileRun).toBeNull();
  });

  it('writes the live synthesis count into the loaded stats', async () => {
    const { result } = await setup();
    await emitIngest(snapshotOf({}, { synthesis_pending_count: 7 }));
    expect(result.current.stats?.synthesis_pending).toBe(7);
  });

  it('has no stats to write the live count into when they failed to load', async () => {
    apiRequest.mockRejectedValue(new Error('down'));
    const { result } = await setup();
    await emitIngest(snapshotOf({}, { synthesis_pending_count: 7 }));
    expect(result.current.stats).toBeNull();
    expect(result.current.synthesisPendingCount).toBe(7);
  });

  it('rereads the raw tree and the stats when the tree is out of sync, and refreshes the tree views', async () => {
    const { result } = await setup('a1');
    service.getRawTree.mockResolvedValue([NODE]);
    await emitIngest(snapshotOf({}, { tree_sync_required: true }));
    // The mount load, the silent tree refresh and the stats reload (which reads the tree again) each fetch it.
    expect(service.getRawTree.mock.calls).toEqual([['a1'], ['a1'], ['a1']]);
    expect(statsLoads()).toBe(2);
    expect(result.current.rawTreeData).toEqual([NODE]);
    expect(result.current.treeSyncNonce).toBe(1);
  });

  it('rereads only the stats when the snapshot asks for a stats refresh', async () => {
    const { result } = await setup();
    await emitIngest(snapshotOf({}, { stats_refresh_required: true }));
    expect(statsLoads()).toBe(2);
    expect(service.getRawTree).toHaveBeenCalledTimes(2);
    expect(result.current.treeSyncNonce).toBe(0);
  });

  it('treats a tree sync as the stronger signal and reloads the stats once', async () => {
    await setup();
    await emitIngest(snapshotOf({}, { tree_sync_required: true, stats_refresh_required: true }));
    expect(statsLoads()).toBe(2);
  });

  it('leaves the tree views alone and logs when the tree refresh fails', async () => {
    const { result } = await setup();
    const failure = new Error('tree down');
    service.getRawTree.mockRejectedValue(failure);
    await emitIngest(snapshotOf({}, { tree_sync_required: true }));
    expect(result.current.treeSyncNonce).toBe(0);
    expect(consoleWarn).toHaveBeenCalledWith('Failed to refresh wiki ingest trees after SSE signal.', failure);
  });

  it('refreshes the tree and bumps the sync nonce on demand', async () => {
    const { result } = await setup();
    service.getRawTree.mockResolvedValue([NODE]);
    await act(() => result.current.refreshIngestTreesSilently());
    expect(result.current.rawTreeData).toEqual([NODE]);
    expect(result.current.treeSyncNonce).toBe(1);
    act(() => result.current.bumpTreeSync());
    expect(result.current.treeSyncNonce).toBe(2);
  });

  it('refreshes the tree of the scope the page is in now, not the one it opened with', async () => {
    const { result, rerender } = await setup('a1');
    rerender({ scopeId: 'a2', activeTab: 'overview' });
    await settle();
    service.getRawTree.mockClear();
    await act(() => result.current.refreshIngestTreesSilently());
    expect(service.getRawTree).toHaveBeenCalledExactlyOnceWith('a2');
  });
});

describe('useWikiOverviewData: noticing the end of work', () => {
  it('rereads the stats when the queue goes from busy to idle, not on the first idle snapshot', async () => {
    await setup();
    await emitIngest(snapshotOf());
    expect(statsLoads()).toBe(1);
    await emitIngest(busySnapshot());
    expect(statsLoads()).toBe(1);
    await emitIngest(snapshotOf());
    expect(statsLoads()).toBe(2);
    await emitIngest(snapshotOf());
    expect(statsLoads()).toBe(2);
  });

  it('does not reread the stats while the queue stays busy', async () => {
    await setup();
    await emitIngest(busySnapshot());
    await emitIngest(busySnapshot());
    expect(statsLoads()).toBe(1);
  });

  it.each([
    ['processing', { processing: 1 }],
    ['pending', { pending: 1 }],
  ])('counts %s items as work', async (_kind, stats) => {
    await setup();
    await emitIngest(snapshotOf(stats));
    await emitIngest(snapshotOf());
    expect(statsLoads()).toBe(2);
  });

  it('keeps counting a paused compile as work until the circuit is resumed', async () => {
    await setup();
    await emitIngest(snapshotOf({}, { compile_run: compileRunOf() }));
    await emitIngest(snapshotOf());
    expect(statsLoads()).toBe(2);
  });

  it('reports a compile this page started once, when its queue drains', async () => {
    const { result } = await setup();
    result.current.markCompileRequested(true);
    await emitIngest(busySnapshot());
    expect(toast.success).not.toHaveBeenCalled();
    await emitIngest(snapshotOf());
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('success.compileFinished|{"tab":"tabs.pendingEdits"}');
    await emitIngest(busySnapshot());
    await emitIngest(snapshotOf());
    expect(toast.success).toHaveBeenCalledOnce();
  });

  it('stays quiet about a queue that this page did not start', async () => {
    await setup();
    await emitIngest(busySnapshot());
    await emitIngest(snapshotOf());
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('stays quiet when the compile it started had nothing to do', async () => {
    const { result } = await setup();
    result.current.markCompileRequested(true);
    result.current.markCompileRequested(false);
    await emitIngest(busySnapshot());
    await emitIngest(snapshotOf());
    expect(toast.success).not.toHaveBeenCalled();
  });
});
