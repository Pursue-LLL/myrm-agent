/** @vitest-environment jsdom */
import { act, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { resetKit, service, toast } from './wikiSectionTestKit';
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

describe('useWikiMaintenance: repairs and reindexing', () => {
  it('repairs page types, reports the count and rereads the stats', async () => {
    const { result, overview } = renderMaintenance('a1');
    await act(() => result.current.handleRepairPageTypes());
    expect(service.repairPageTypes).toHaveBeenCalledExactlyOnceWith('a1');
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('success.repairTypesComplete|{"count":2}');
    expect(overview.loadStats).toHaveBeenCalledOnce();
    expect(result.current.isRepairingTypes).toBe(false);
  });

  it.each([
    ['page types', 'isRepairingTypes', 'repairPageTypes', 'handleRepairPageTypes'],
    ['publication state', 'isRepairingPublication', 'repairPublication', 'handleRepairPublication'],
  ] as const)('reports the repair of the %s while it runs', async (_label, flag, method, handler) => {
    const pending = deferred<never>();
    service[method].mockReturnValue(pending.promise);
    const { result } = renderMaintenance();
    let repairing: Promise<void> = Promise.resolve();
    act(() => {
      repairing = result.current[handler]();
    });
    expect(result.current[flag]).toBe(true);
    pending.reject(new Error('stopped'));
    await act(() => repairing);
    expect(result.current[flag]).toBe(false);
  });

  it('warns with the counts when the type repair only partly succeeded, and still rereads the stats', async () => {
    service.repairPageTypes.mockResolvedValue({
      success: false,
      files_scanned: 9,
      files_repaired: 4,
      files_skipped: 3,
      message: 'Repaired 4 of 9 scanned files; 2 errors',
    });
    const { result, overview } = renderMaintenance();
    await act(() => result.current.handleRepairPageTypes());
    expect(toast.warning).toHaveBeenCalledExactlyOnceWith('errors.repairTypesPartial|{"repaired":4,"scanned":9}');
    expect(toast.success).not.toHaveBeenCalled();
    expect(overview.loadStats).toHaveBeenCalledOnce();
  });

  it('reports a failed type repair and logs it', async () => {
    const failure = new Error('boom');
    service.repairPageTypes.mockRejectedValue(failure);
    const { result, overview } = renderMaintenance();
    await act(() => result.current.handleRepairPageTypes());
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.repairTypesFailed');
    expect(overview.loadStats).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith('Repair page types failed:', failure);
    expect(result.current.isRepairingTypes).toBe(false);
  });

  it('repairs publication and reports what was repaired and reindexed', async () => {
    const { result, overview } = renderMaintenance('a1');
    await act(() => result.current.handleRepairPublication());
    expect(service.repairPublication).toHaveBeenCalledExactlyOnceWith('a1');
    expect(toast.success).toHaveBeenCalledExactlyOnceWith(
      'success.repairPublicationComplete|{"repaired":2,"reindexed":1}',
    );
    expect(overview.loadStats).toHaveBeenCalledOnce();
  });

  it('mentions the drafts it left alone on purpose', async () => {
    service.repairPublication.mockResolvedValue({
      success: true,
      files_scanned: 9,
      files_repaired: 2,
      files_skipped: 3,
      files_skipped_intentional_drafts: 3,
      reindexed: 1,
      message: 'ok',
    });
    const { result } = renderMaintenance();
    await act(() => result.current.handleRepairPublication());
    expect(toast.success).toHaveBeenCalledExactlyOnceWith(
      'success.repairPublicationCompleteWithSkips|{"repaired":2,"reindexed":1,"skippedDrafts":3}',
    );
  });

  it('warns with the counts when the publication repair only partly succeeded, and reports a failed one', async () => {
    service.repairPublication.mockResolvedValueOnce({
      success: false,
      files_scanned: 9,
      files_repaired: 2,
      files_skipped: 3,
      reindexed: 1,
      message: 'Repaired 2 of 9 scanned files; reindexed 1; 1 errors',
    });
    const { result, overview } = renderMaintenance();
    await act(() => result.current.handleRepairPublication());
    expect(toast.warning).toHaveBeenCalledExactlyOnceWith(
      'errors.repairPublicationPartial|{"repaired":2,"scanned":9,"reindexed":1}',
    );
    expect(overview.loadStats).toHaveBeenCalledOnce();

    const failure = new Error('boom');
    service.repairPublication.mockRejectedValueOnce(failure);
    await act(() => result.current.handleRepairPublication());
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.repairPublicationFailed');
    expect(overview.loadStats).toHaveBeenCalledOnce();
    expect(consoleError).toHaveBeenCalledWith('Repair publication failed:', failure);
    expect(result.current.isRepairingPublication).toBe(false);
  });

  it('reindexes vectors, reports the counts, rereads the stats and refreshes the tree views', async () => {
    const { result, overview } = renderMaintenance('a1');
    await act(() => result.current.handleReindexVectors());
    expect(service.reindexVectors).toHaveBeenCalledExactlyOnceWith('a1');
    expect(toast.success).toHaveBeenCalledExactlyOnceWith(
      'success.reindexVectorsComplete|{"concepts":1,"sidecars":2,"assets":3}',
    );
    expect(overview.loadStats).toHaveBeenCalledOnce();
    expect(overview.bumpTreeSync).toHaveBeenCalledOnce();
    expect(result.current.isReindexingVectors).toBe(false);
    expect(result.current.reindexErrors).toEqual([]);
  });

  it('keeps the errors of a partial reindex and clears them when the next one starts', async () => {
    service.reindexVectors.mockResolvedValueOnce({
      success: false,
      scanned: 3,
      reindexed: 1,
      concepts_reindexed: 1,
      sidecars_reindexed: 0,
      assets_indexed: 0,
      skipped_drafts: 0,
      failed: 2,
      errors: ['a.md: bad', 'b.md: bad'],
      message: 'partly reindexed',
    });
    const { result } = renderMaintenance();
    await act(() => result.current.handleReindexVectors());
    expect(result.current.reindexErrors).toEqual(['a.md: bad', 'b.md: bad']);
    expect(toast.warning).toHaveBeenCalledExactlyOnceWith(
      'errors.reindexVectorsPartial|{"concepts":1,"sidecars":0,"assets":0,"failed":2}',
    );

    const pending = deferred<never>();
    service.reindexVectors.mockReturnValue(pending.promise);
    let again: Promise<void> = Promise.resolve();
    act(() => {
      again = result.current.handleReindexVectors();
    });
    expect(result.current.reindexErrors).toEqual([]);
    expect(result.current.isReindexingVectors).toBe(true);
    pending.reject(new Error('stopped'));
    await act(() => again);
  });

  it('treats a reindex answer without an error list as no errors', async () => {
    service.reindexVectors.mockResolvedValueOnce({
      success: true,
      scanned: 3,
      reindexed: 3,
      concepts_reindexed: 1,
      sidecars_reindexed: 2,
      assets_indexed: 0,
      skipped_drafts: 0,
      failed: 0,
      message: 'reindexed',
    });
    const { result } = renderMaintenance();
    await act(() => result.current.handleReindexVectors());
    expect(result.current.reindexErrors).toEqual([]);
  });

  it('reports a failed reindex and logs it, leaving the tree views alone', async () => {
    const failure = new Error('boom');
    service.reindexVectors.mockRejectedValue(failure);
    const { result, overview } = renderMaintenance();
    await act(() => result.current.handleReindexVectors());
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.reindexVectorsFailed');
    expect(overview.loadStats).not.toHaveBeenCalled();
    expect(overview.bumpTreeSync).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith('Reindex wiki vectors failed:', failure);
    expect(result.current.isReindexingVectors).toBe(false);
  });
});
