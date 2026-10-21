import { describe, it, expect, beforeEach } from 'vitest';
import { useDataMigrationStore } from '../useDataMigrationStore';
import { FourDimensionalAssets } from '../dataMigrationTypes';

describe('useDataMigrationStore', () => {
  beforeEach(() => {
    useDataMigrationStore.getState().reset();
  });

  const mockIncomingAssets: FourDimensionalAssets = {
    tasks: [
      { id: 't1', title: '旧版数据分析', createdAt: Date.now(), status: 'completed' },
    ],
    cronJobs: [
      { id: 'c1', name: '凌晨打卡', cronExpression: '0 0 * * *', taskTemplate: 'sign', enabled: true },
    ],
    memories: [
      { id: 'm1', category: 'project', content: '使用 Next.js', confidence: 0.9, createdAt: Date.now() },
    ],
    mcpConfigs: [
      { name: 'sqlite-mcp', transport: 'stdio', enabled: true },
    ],
  };

  it('initializes with default settings', () => {
    const state = useDataMigrationStore.getState();
    expect(state.status).toBe('idle');
    expect(state.autoSilentImportEnabled).toBe(true);
    expect(state.showSilentToast).toBe(false);
    expect(state.isReconciliationModalOpen).toBe(false);
    expect(state.conflictStrategy).toBe('skip');
  });

  it('triggers silent detection and pops toast notification', () => {
    useDataMigrationStore.getState().triggerSilentDetection('qoder_v1', mockIncomingAssets);

    const state = useDataMigrationStore.getState();
    expect(state.showSilentToast).toBe(true);
    expect(state.activeReport?.tasks.total).toBe(1);
    expect(state.activeReport?.sourceType).toBe('qoder_v1');
    expect(state.logs.length).toBeGreaterThan(0);
  });

  it('bypasses silent detection when autoSilentImportEnabled is false', () => {
    useDataMigrationStore.getState().setAutoSilentImportEnabled(false);
    useDataMigrationStore.getState().triggerSilentDetection('qoder_v1');

    const state = useDataMigrationStore.getState();
    expect(state.showSilentToast).toBe(false);
    expect(state.activeReport).toBeNull();
  });

  it('loads incoming data manually and opens reconciliation modal', () => {
    useDataMigrationStore.getState().loadIncomingData(mockIncomingAssets, 'hermes_legacy', '~/.hermes');

    const state = useDataMigrationStore.getState();
    expect(state.isReconciliationModalOpen).toBe(true);
    expect(state.activeReport?.sourceType).toBe('hermes_legacy');
    expect(state.activeReport?.tasks.total).toBe(1);
    expect(state.incomingAssets).toEqual(mockIncomingAssets);
  });

  it('updates conflict strategy and recalculates report', () => {
    useDataMigrationStore.getState().loadIncomingData(mockIncomingAssets, 'openclaw');
    useDataMigrationStore.getState().setConflictStrategy('overwrite');

    expect(useDataMigrationStore.getState().conflictStrategy).toBe('overwrite');
    expect(useDataMigrationStore.getState().activeReport?.conflictStrategy).toBe('overwrite');
  });

  it('executes import and adds asset fingerprints to local cache', () => {
    useDataMigrationStore.getState().loadIncomingData(mockIncomingAssets, 'sqlite_backup');
    const result = useDataMigrationStore.getState().executeImport();

    expect(result).not.toBeNull();
    expect(result?.tasks).toHaveLength(1);
    expect(result?.cronJobs).toHaveLength(1);

    const state = useDataMigrationStore.getState();
    expect(state.status).toBe('completed');
    expect(state.isReconciliationModalOpen).toBe(false);
    expect(state.showSilentToast).toBe(false);
    expect(state.existingFingerprints.has('task:旧版数据分析')).toBe(true);
    expect(state.existingFingerprints.has('cron:凌晨打卡:0 0 * * *')).toBe(true);
  });

  it('dismisses silent toast and toggles modal correctly', () => {
    useDataMigrationStore.getState().triggerSilentDetection('qoder_v1', mockIncomingAssets);
    expect(useDataMigrationStore.getState().showSilentToast).toBe(true);

    useDataMigrationStore.getState().dismissSilentToast();
    expect(useDataMigrationStore.getState().showSilentToast).toBe(false);

    useDataMigrationStore.getState().toggleReconciliationModal(true);
    expect(useDataMigrationStore.getState().isReconciliationModalOpen).toBe(true);
  });
});
