/** @vitest-environment jsdom */
import { act, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import {
  MockedApiError,
  finishMaintainRun,
  maintainRun,
  patchMaintainRun,
  resetKit,
  service,
  toast,
} from './wikiSectionTestKit';
import { compileRunOf, driftIssue, healthOf, maintainResultOf, snapshotOf } from './wikiSectionFixtures';
import { renderMaintenance } from './wikiMaintenanceHarness';

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  resetKit();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  consoleError.mockRestore();
});

describe('useWikiMaintenance: compiling', () => {
  it('hands the compile to the background, remembers that this page asked, and says how much is queued', async () => {
    const { result, overview, handleWikiTabChange } = renderMaintenance('a1');
    await act(() => result.current.handleCompile());
    expect(service.compileWiki).toHaveBeenCalledExactlyOnceWith('a1');
    expect(overview.setCompileRun).toHaveBeenCalledExactlyOnceWith(null);
    expect(overview.markCompileRequested).toHaveBeenCalledExactlyOnceWith(true);
    expect(toast.message).toHaveBeenCalledExactlyOnceWith('success.compileStarted|{"count":3}');
    expect(overview.loadStats).toHaveBeenCalledOnce();
    expect(handleWikiTabChange).not.toHaveBeenCalled();
    expect(result.current.isCompiling).toBe(false);
  });

  it('locks the compile button while the request is in flight', async () => {
    const pending = deferred<{ pending: number }>();
    service.compileWiki.mockReturnValue(pending.promise);
    const { result } = renderMaintenance();
    let compiling: Promise<void> = Promise.resolve();
    act(() => {
      compiling = result.current.handleCompile();
    });
    expect(result.current.isCompiling).toBe(true);
    expect(result.current.isWikiCompileBusy).toBe(true);
    pending.resolve({ pending: 1 });
    await act(() => compiling);
    expect(result.current.isCompiling).toBe(false);
    expect(result.current.isWikiCompileBusy).toBe(false);
  });

  it('says there is nothing new to compile and does not expect a finish', async () => {
    service.compileWiki.mockResolvedValue({ pending: 0, compile_run: null });
    const { result, overview } = renderMaintenance();
    await act(() => result.current.handleCompile());
    expect(overview.markCompileRequested).toHaveBeenCalledExactlyOnceWith(false);
    expect(toast.message).toHaveBeenCalledExactlyOnceWith('success.compileNothingNew');
    expect(overview.loadStats).toHaveBeenCalledOnce();
  });

  it('explains a paused compile circuit with its own reason and opens the queue', async () => {
    const run = compileRunOf({ pause_reason: 'Quota exhausted' });
    service.compileWiki.mockResolvedValue({ pending: 2, compile_run: run });
    const { result, overview, handleWikiTabChange } = renderMaintenance();
    await act(() => result.current.handleCompile());
    expect(overview.setCompileRun).toHaveBeenCalledExactlyOnceWith(run);
    expect(toast.warning).toHaveBeenCalledExactlyOnceWith('Quota exhausted');
    expect(handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('queue');
    expect(toast.message).not.toHaveBeenCalled();
    expect(overview.loadStats).toHaveBeenCalledOnce();
  });

  it('falls back to the default pause reason when the server gave none', async () => {
    service.compileWiki.mockResolvedValue({ pending: 2, compile_run: compileRunOf({ pause_reason: '' }) });
    const { result } = renderMaintenance();
    await act(() => result.current.handleCompile());
    expect(toast.warning).toHaveBeenCalledExactlyOnceWith('compileRun.pausedDefaultReason');
  });

  it('treats a running circuit like a normal start', async () => {
    service.compileWiki.mockResolvedValue({ pending: 2, compile_run: compileRunOf({ state: 'running' }) });
    const { result, handleWikiTabChange } = renderMaintenance();
    await act(() => result.current.handleCompile());
    expect(toast.warning).not.toHaveBeenCalled();
    expect(toast.message).toHaveBeenCalledExactlyOnceWith('success.compileStarted|{"count":2}');
    expect(handleWikiTabChange).not.toHaveBeenCalled();
  });

  it('sends a compile the dedup gate blocked to the duplicate review instead of calling it a failure', async () => {
    service.compileWiki.mockRejectedValue(new MockedApiError('blocked', 409));
    const { result, overview, handleWikiTabChange } = renderMaintenance();
    await act(() => result.current.handleCompile());
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.compileBlockedByDedup');
    expect(handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
    expect(overview.loadStats).not.toHaveBeenCalled();
    expect(result.current.isCompiling).toBe(false);
  });

  it.each([
    ['another API error', new MockedApiError('server', 500)],
    ['a plain error', new Error('boom')],
  ])('reports %s as a failed compile and logs it', async (_label, failure) => {
    service.compileWiki.mockRejectedValue(failure);
    const { result, handleWikiTabChange } = renderMaintenance();
    await act(() => result.current.handleCompile());
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.compileFailed');
    expect(handleWikiTabChange).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith('Compile failed:', failure);
    expect(result.current.isCompiling).toBe(false);
  });

  it('counts a file in flight on the live queue as a compile in progress', () => {
    const idle = renderMaintenance(null, snapshotOf());
    expect(idle.result.current.isWikiCompileBusy).toBe(false);
    const busy = renderMaintenance(null, snapshotOf({ processing: 1 }));
    expect(busy.result.current.isWikiCompileBusy).toBe(true);
  });
});

describe('useWikiMaintenance: resuming the compile circuit', () => {
  it('resumes it for the scope, confirms and rereads the stats', async () => {
    const pending = deferred<undefined>();
    service.resumeCompileCircuit.mockReturnValue(pending.promise);
    const { result, overview } = renderMaintenance('a1');
    let resuming: Promise<void> = Promise.resolve();
    act(() => {
      resuming = result.current.handleResumeCompile();
    });
    expect(result.current.isResumingCompile).toBe(true);
    pending.resolve(undefined);
    await act(() => resuming);
    expect(service.resumeCompileCircuit).toHaveBeenCalledExactlyOnceWith('a1');
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('compileRun.resumeSuccess');
    expect(overview.loadStats).toHaveBeenCalledOnce();
    expect(result.current.isResumingCompile).toBe(false);
  });

  it('reports a failed resume and logs it', async () => {
    const failure = new Error('still paused');
    service.resumeCompileCircuit.mockRejectedValue(failure);
    const { result, overview } = renderMaintenance();
    await act(() => result.current.handleResumeCompile());
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('compileRun.resumeFailed');
    expect(toast.success).not.toHaveBeenCalled();
    expect(overview.loadStats).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith('Resume compile failed:', failure);
    expect(result.current.isResumingCompile).toBe(false);
  });
});

describe('useWikiMaintenance: maintenance runs', () => {
  it('follows the run of the scope and starts it in the chosen mode', () => {
    const { result } = renderMaintenance('a1');
    expect(maintainRun.scope).toBe('a1');
    expect(result.current.maintainMode).toBe('structural');
    act(() => result.current.handleMaintain());
    expect(maintainRun.start).toHaveBeenLastCalledWith('structural');
    act(() => result.current.setMaintainMode('full'));
    act(() => result.current.handleMaintain());
    expect(maintainRun.start).toHaveBeenLastCalledWith('full');
  });

  it('mirrors the run: busy, stoppable, stopping and which model phase it is in', () => {
    const { result } = renderMaintenance();
    expect(result.current.isMaintaining).toBe(false);
    expect(result.current.canCancelMaintain).toBe(false);
    expect(result.current.isCancellingMaintain).toBe(false);
    expect(result.current.maintainProgressLabel).toBeNull();

    patchMaintainRun({ isRunning: true, canCancel: true, progress: { phase: 'drift_review', done: 1, total: 4 } });
    expect(result.current.isMaintaining).toBe(true);
    expect(result.current.canCancelMaintain).toBe(true);
    expect(result.current.maintainProgressLabel).toEqual({
      key: 'maintainProgress.driftReview',
      values: { done: 1, total: 4 },
    });

    patchMaintainRun({ isCancelling: true, progress: { phase: 'link_discovery', done: 2, total: 3 } });
    expect(result.current.isCancellingMaintain).toBe(true);
    expect(result.current.maintainProgressLabel).toEqual({
      key: 'maintainProgress.linkDiscovery',
      values: { done: 2, total: 3 },
    });
  });

  it('asks the run to stop, and tells the user when that did not go through', async () => {
    const { result } = renderMaintenance();
    await act(() => result.current.handleCancelMaintain());
    expect(maintainRun.cancel).toHaveBeenCalledOnce();
    expect(toast.error).not.toHaveBeenCalled();

    const failure = new Error('cannot stop');
    maintainRun.cancel.mockRejectedValue(failure);
    await act(() => result.current.handleCancelMaintain());
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.maintainCancelFailed');
    expect(consoleError).toHaveBeenCalledWith('Failed to cancel wiki maintenance:', failure);
  });
});

describe('useWikiMaintenance: when a run ends', () => {
  it.each([
    ['compile_busy', 'errors.maintainCompileBusy'],
    ['failed', 'errors.maintainFailed'],
  ] as const)('reports a %s run with its own message and changes nothing else', async (reason, message) => {
    const { overview } = renderMaintenance();
    await finishMaintainRun({ kind: 'failure', reason });
    expect(toast.error).toHaveBeenCalledExactlyOnceWith(message);
    expect(overview.loadStats).not.toHaveBeenCalled();
    expect(overview.setHealthReport).not.toHaveBeenCalled();
    expect(overview.bumpTreeSync).not.toHaveBeenCalled();
  });

  it.each([
    [
      'links found',
      maintainResultOf(),
      'success',
      'success.maintainSummaryWithLinks|{"found":4,"fixed":2,"connections":1}',
    ],
    [
      'open actions left',
      maintainResultOf({ open_actions_count: 3 }),
      'message',
      'healthReport.maintainToastOpen|{"open":3,"fixed":2}',
    ],
    ['the model unavailable', maintainResultOf({ ai_unavailable: true }), 'warning', 'errors.maintainAiUnavailable'],
    [
      'nothing to report',
      maintainResultOf({ issues_fixed: 0, connections_discovered: 0 }),
      'success',
      'success.maintainComplete',
    ],
  ] as const)('picks the toast for a finished run with %s', async (_label, result, variant, text) => {
    renderMaintenance();
    await finishMaintainRun({ kind: 'success', mode: 'structural', result });
    expect(toast[variant]).toHaveBeenCalledExactlyOnceWith(text);
  });

  it('says a stopped run was cancelled', async () => {
    renderMaintenance();
    await finishMaintainRun({
      kind: 'cancelled',
      mode: 'full',
      result: maintainResultOf({ connections_discovered: 0 }),
    });
    expect(toast.message).toHaveBeenCalledExactlyOnceWith('success.maintainCancelled');
  });

  it('opens the health report, rereads the stats, rebuilds the report and refreshes the tree views in that order', async () => {
    const order: string[] = [];
    const reload = deferred<undefined>();
    const { overview } = renderMaintenance();
    vi.mocked(overview.setHealthReportExpanded).mockImplementation(() => void order.push('expand'));
    vi.mocked(overview.loadStats).mockImplementation(async () => {
      order.push('stats');
      await reload.promise;
      order.push('stats done');
    });
    vi.mocked(overview.setHealthReport).mockImplementation(() => void order.push('report'));
    vi.mocked(overview.bumpTreeSync).mockImplementation(() => void order.push('tree'));
    const finished = finishMaintainRun({ kind: 'success', mode: 'full', result: maintainResultOf() });
    await settle();
    expect(order).toEqual(['expand', 'stats']);
    reload.resolve(undefined);
    await finished;
    expect(order).toEqual(['expand', 'stats', 'stats done', 'report', 'tree']);
    expect(overview.setHealthReportExpanded).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('rebuilds the health report from the run and keeps the cross-links of the previous report', async () => {
    const result = maintainResultOf({ open_actions_count: 2, issues_found: 5, issues: [driftIssue] });
    const { overview } = renderMaintenance();
    await finishMaintainRun({ kind: 'success', mode: 'full', result });
    const update = vi.mocked(overview.setHealthReport).mock.calls[0][0] as (
      previous: ReturnType<typeof healthOf> | null,
    ) => ReturnType<typeof healthOf>;
    const rebuilt = update(healthOf({ duplicate_groups_pending: 2, synthesis_pending: 4 }));
    expect(rebuilt).toMatchObject({
      mode: 'full',
      open_actions_count: 2,
      issues_found: 5,
      issues: [driftIssue],
      drift_sampled: true,
      duplicate_groups_pending: 2,
      synthesis_pending: 4,
    });
    expect(update(null)).toMatchObject({ duplicate_groups_pending: 0, synthesis_pending: 0 });
  });
});
