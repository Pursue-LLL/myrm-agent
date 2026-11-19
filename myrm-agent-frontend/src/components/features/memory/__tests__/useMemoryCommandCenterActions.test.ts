/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../hooks/useMemoryCommandCenterActions::useMemoryCommandCenterActions (POS: 命令中心写操作处理器)
 *
 * [OUTPUT]
 * useMemoryCommandCenterActions tests: 自动整理撤销的结果提示、失败提示与刷新时机；导入回滚后设置行的重载时机。
 *
 * [POS]
 * 命令中心写操作 hook 回归测试。撤销无论成功、部分失败还是被服务端拒绝（该次整理已被撤销或被取代）都要刷新快照，
 * 否则撤销卡片会继续展示一次已经不能撤销的整理；导入回滚只有服务端确实完成后才重载前端缓存的设置行。
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMemoryCommandCenterActions } from '../hooks/useMemoryCommandCenterActions';

const toast = vi.fn();
const undoConsolidation = vi.fn();
const dryRunRollbackMemoryImport = vi.fn();
const rollbackMemoryImport = vi.fn();
const reloadMigratedConfigs = vi.fn();
const router = { push: vi.fn() };

vi.mock('@/hooks/shared/useToast', () => ({
  toast: (...args: unknown[]) => toast(...args),
}));

vi.mock('@/services/memory/consolidationUndo', () => ({
  undoConsolidation: (...args: unknown[]) => undoConsolidation(...args),
}));

vi.mock('@/services/memory/archive', () => ({
  dryRunRollbackMemoryImport: (...args: unknown[]) => dryRunRollbackMemoryImport(...args),
  rollbackMemoryImport: (...args: unknown[]) => rollbackMemoryImport(...args),
  exportMemoryArchive: vi.fn(),
}));

vi.mock('@/services/memory/migratedConfigReload', () => ({
  reloadMigratedConfigs: (...args: unknown[]) => reloadMigratedConfigs(...args),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => router,
}));

// Renders the interpolated values into the text so the assertions can see which counts reached the toast.
const stableT = (key: string, values?: Record<string, number>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const loadSnapshot = vi.fn();
const setActionId = vi.fn();

const renderActions = () =>
  renderHook(() =>
    useMemoryCommandCenterActions({
      loadSnapshot,
      setActionId,
      showVerifySection: vi.fn(),
      setDiagnosticRun: vi.fn(),
    }),
  );

describe('useMemoryCommandCenterActions.handleConsolidationUndo', () => {
  const undo = async (cycleId: string) => {
    const { result } = renderActions();
    await act(async () => {
      await result.current.handleConsolidationUndo(cycleId);
    });
  };

  beforeEach(() => {
    vi.clearAllMocks();
    loadSnapshot.mockResolvedValue(undefined);
  });

  it('undoes the cycle the user was shown and reports the counts', async () => {
    undoConsolidation.mockResolvedValue({ rolled_back: 3, skipped_conflict: 1, errors: 0 });

    await undo('cycle-1');

    expect(undoConsolidation).toHaveBeenCalledTimes(1);
    expect(undoConsolidation).toHaveBeenCalledWith('cycle-1');
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({
      title: 'commandCenter.consolidationUndoSuccess',
      description: 'commandCenter.consolidationUndoSuccessDesc:{"count":3,"conflicts":1}',
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(1);
    expect(setActionId.mock.calls).toEqual([['consolidation:undo'], [null]]);
  });

  it('reports a partial undo as a failure with the error and conflict counts', async () => {
    undoConsolidation.mockResolvedValue({ rolled_back: 2, skipped_conflict: 1, errors: 2 });

    await undo('cycle-1');

    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({
      title: 'commandCenter.consolidationUndoPartial',
      description: 'commandCenter.consolidationUndoPartialDesc:{"count":2,"errors":2,"conflicts":1}',
      variant: 'destructive',
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(1);
  });

  it('shows the server refusal and still refreshes so a stale card disappears', async () => {
    undoConsolidation.mockRejectedValue(new Error('This consolidation can no longer be undone'));

    await undo('stale-cycle');

    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({
      title: 'commandCenter.actionFailed',
      description: 'This consolidation can no longer be undone',
      variant: 'destructive',
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(1);
    expect(setActionId.mock.calls).toEqual([['consolidation:undo'], [null]]);
  });

  it('falls back to the generic message when the rejection is not an Error', async () => {
    undoConsolidation.mockRejectedValue('boom');

    await undo('cycle-1');

    expect(toast).toHaveBeenCalledWith({
      title: 'commandCenter.actionFailed',
      description: 'unknownError',
      variant: 'destructive',
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(1);
  });
});

describe('useMemoryCommandCenterActions.confirmRollbackImport', () => {
  const rolledBack = { total_rolled_back: 4, missing_items: 0, failed_items: 0 };

  // The confirm step acts on the batch the preview put in state, so the preview has to be rendered before it runs.
  const confirmRollback = async () => {
    const { result } = renderActions();
    await act(async () => {
      await result.current.previewRollbackImport('batch-1');
    });
    await act(async () => {
      await result.current.confirmRollbackImport();
    });
    return result;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    loadSnapshot.mockResolvedValue(undefined);
    reloadMigratedConfigs.mockResolvedValue(undefined);
    dryRunRollbackMemoryImport.mockResolvedValue({ import_batch_id: 'batch-1' });
  });

  it('reloads the cached settings once the server has restored them, then shows the result', async () => {
    rollbackMemoryImport.mockResolvedValue(rolledBack);

    const result = await confirmRollback();

    expect(rollbackMemoryImport).toHaveBeenCalledExactlyOnceWith('batch-1');
    expect(reloadMigratedConfigs).toHaveBeenCalledOnce();
    expect(rollbackMemoryImport.mock.invocationCallOrder[0]).toBeLessThan(
      reloadMigratedConfigs.mock.invocationCallOrder[0],
    );
    expect(result.current.rollbackResult).toEqual(rolledBack);
    expect(loadSnapshot).toHaveBeenCalledTimes(1);
  });

  it('leaves the cached settings alone when the server refused the rollback', async () => {
    rollbackMemoryImport.mockRejectedValue(new Error('This import can no longer be rolled back'));

    const result = await confirmRollback();

    expect(reloadMigratedConfigs).not.toHaveBeenCalled();
    expect(result.current.rollbackResult).toBeNull();
    expect(toast).toHaveBeenCalledWith({
      title: 'commandCenter.actionFailed',
      description: 'This import can no longer be rolled back',
      variant: 'destructive',
    });
  });
});
