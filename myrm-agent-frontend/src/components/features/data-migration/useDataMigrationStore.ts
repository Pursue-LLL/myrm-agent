import { create } from 'zustand';
import {
  ConflictStrategy,
  FourDimensionalAssets,
  MigrationLogEntry,
  MigrationReconciliationReport,
  MigrationSourceType,
  MigrationStatus,
} from './dataMigrationTypes';
import {
  applyConflictResolution,
  buildReconciliationReport,
  generateAssetFingerprint,
} from './dataMigrationEngine';

export interface DataMigrationStoreState {
  status: MigrationStatus;
  autoSilentImportEnabled: boolean;
  showSilentToast: boolean;
  isReconciliationModalOpen: boolean;
  activeReport: MigrationReconciliationReport | null;
  incomingAssets: FourDimensionalAssets | null;
  conflictStrategy: ConflictStrategy;
  existingFingerprints: Set<string>;
  logs: MigrationLogEntry[];
  importProgress: number;

  // Actions
  triggerSilentDetection: (
    sourceType?: MigrationSourceType,
    mockAssets?: FourDimensionalAssets
  ) => void;
  loadIncomingData: (
    assets: FourDimensionalAssets,
    sourceType: MigrationSourceType,
    sourcePath?: string
  ) => void;
  setConflictStrategy: (strategy: ConflictStrategy) => void;
  executeImport: () => FourDimensionalAssets | null;
  dismissSilentToast: () => void;
  toggleReconciliationModal: (open?: boolean) => void;
  setAutoSilentImportEnabled: (enabled: boolean) => void;
  reset: () => void;
}

export const useDataMigrationStore = create<DataMigrationStoreState>((set, get) => ({
  status: 'idle',
  autoSilentImportEnabled: true,
  showSilentToast: false,
  isReconciliationModalOpen: false,
  activeReport: null,
  incomingAssets: null,
  conflictStrategy: 'skip',
  existingFingerprints: new Set<string>(),
  logs: [],
  importProgress: 0,

  triggerSilentDetection: (
    sourceType: MigrationSourceType = 'qoder_v1',
    mockAssets?: FourDimensionalAssets
  ) => {
    const { autoSilentImportEnabled, existingFingerprints } = get();
    if (!autoSilentImportEnabled) {
      return;
    }

    set({ status: 'scanning', importProgress: 20 });

    const assetsToLoad: FourDimensionalAssets = mockAssets || {
      tasks: [
        {
          id: 'task-qoder-01',
          title: '自动化构建财务日报',
          createdAt: Date.now() - 86400000,
          status: 'completed',
        },
      ],
      cronJobs: [
        {
          id: 'cron-qoder-01',
          name: '每日零点数据备份',
          cronExpression: '0 0 * * *',
          taskTemplate: 'run_backup',
          enabled: true,
        },
      ],
      memories: [
        {
          id: 'mem-qoder-01',
          category: 'preference',
          content: '优先采用 TypeScript 严格模式',
          confidence: 0.95,
          createdAt: Date.now() - 86400000,
        },
      ],
      mcpConfigs: [
        {
          name: 'filesystem-server',
          transport: 'stdio',
          command: 'npx',
          args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
          enabled: true,
        },
      ],
    };

    const report = buildReconciliationReport(
      assetsToLoad,
      existingFingerprints,
      sourceType,
      '~/.qoder/config/legacy.json',
      get().conflictStrategy
    );

    const logEntry: MigrationLogEntry = {
      id: `log-${Date.now()}`,
      timestamp: Date.now(),
      level: 'info',
      message: `检测到旧版 ${sourceType} 资产，已生成对账单 (任务:${report.tasks.total}, 定时:${report.cronJobs.total}, 记忆:${report.memories.total}, MCP:${report.mcpConfigs.total})`,
    };

    set((state) => ({
      status: 'idle',
      activeReport: report,
      incomingAssets: assetsToLoad,
      showSilentToast: true,
      importProgress: 100,
      logs: [logEntry, ...state.logs],
    }));
  },

  loadIncomingData: (assets, sourceType, sourcePath) => {
    const { existingFingerprints, conflictStrategy } = get();
    set({ status: 'reconciling' });

    const report = buildReconciliationReport(
      assets,
      existingFingerprints,
      sourceType,
      sourcePath,
      conflictStrategy
    );

    const logEntry: MigrationLogEntry = {
      id: `log-${Date.now()}`,
      timestamp: Date.now(),
      level: 'info',
      message: `手动加载 ${sourceType} 归档，等待对账确认`,
    };

    set((state) => ({
      status: 'idle',
      incomingAssets: assets,
      activeReport: report,
      isReconciliationModalOpen: true,
      logs: [logEntry, ...state.logs],
    }));
  },

  setConflictStrategy: (strategy) => {
    const { incomingAssets, existingFingerprints, activeReport } = get();
    let updatedReport = activeReport;
    if (incomingAssets && activeReport) {
      updatedReport = buildReconciliationReport(
        incomingAssets,
        existingFingerprints,
        activeReport.sourceType,
        activeReport.sourcePath,
        strategy
      );
    }
    set({ conflictStrategy: strategy, activeReport: updatedReport });
  },

  executeImport: () => {
    const { incomingAssets, existingFingerprints, conflictStrategy } = get();
    if (!incomingAssets) {
      return null;
    }

    set({ status: 'importing', importProgress: 50 });

    const finalAssets = applyConflictResolution(
      incomingAssets,
      existingFingerprints,
      conflictStrategy
    );

    // 更新本地指纹缓存
    const newFingerprints = new Set(existingFingerprints);
    finalAssets.tasks.forEach((t) =>
      newFingerprints.add(generateAssetFingerprint('task', t))
    );
    finalAssets.cronJobs.forEach((c) =>
      newFingerprints.add(generateAssetFingerprint('cron', c))
    );
    finalAssets.memories.forEach((m) =>
      newFingerprints.add(generateAssetFingerprint('memory', m))
    );
    finalAssets.mcpConfigs.forEach((m) =>
      newFingerprints.add(generateAssetFingerprint('mcp', m))
    );

    const logEntry: MigrationLogEntry = {
      id: `log-${Date.now()}`,
      timestamp: Date.now(),
      level: 'info',
      message: `迁移对账完成：成功导入 ${finalAssets.tasks.length} 项任务，${finalAssets.cronJobs.length} 项定时作业，${finalAssets.memories.length} 条记忆，${finalAssets.mcpConfigs.length} 个 MCP 服务`,
    };

    set((state) => ({
      status: 'completed',
      existingFingerprints: newFingerprints,
      importProgress: 100,
      isReconciliationModalOpen: false,
      showSilentToast: false,
      logs: [logEntry, ...state.logs],
    }));

    return finalAssets;
  },

  dismissSilentToast: () => {
    set({ showSilentToast: false });
  },

  toggleReconciliationModal: (open) => {
    set((state) => ({
      isReconciliationModalOpen:
        typeof open === 'boolean' ? open : !state.isReconciliationModalOpen,
    }));
  },

  setAutoSilentImportEnabled: (enabled) => {
    set({ autoSilentImportEnabled: enabled });
  },

  reset: () => {
    set({
      status: 'idle',
      autoSilentImportEnabled: true,
      showSilentToast: false,
      isReconciliationModalOpen: false,
      activeReport: null,
      incomingAssets: null,
      conflictStrategy: 'skip',
      existingFingerprints: new Set<string>(),
      logs: [],
      importProgress: 0,
    });
  },
}));
