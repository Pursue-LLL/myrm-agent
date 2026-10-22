import { create } from 'zustand';
import type {
  AntiDowngradeTelemetry,
  AutostartAuthorizationState,
  CostBudgetGateConfig,
  DaemonProcessMetrics,
  MicroDeltaOtaInfo,
  StepSaverMetrics,
  ZeroTrespassSuiteState,
} from './zeroTrespassTypes';

interface ZeroTrespassActions {
  setAutostartAuth: (state: AutostartAuthorizationState) => void;
  updateDaemonMetrics: (metrics: Partial<DaemonProcessMetrics>) => void;
  killAndCleanZombieProcess: () => void;
  setBudgetEstimation: (estimatedTokens: number, estimatedCostUsd: number) => void;
  confirmBudgetGate: () => void;
  recordTelemetry: (telemetry: Omit<AntiDowngradeTelemetry, 'isDowngradeDetected'>) => void;
  recordStepSaver: (metrics: StepSaverMetrics) => void;
  updateDeltaOtaStatus: (info: Partial<MicroDeltaOtaInfo>) => void;
  toggleByok: (active?: boolean) => void;
  resetState: () => void;
}

export type ZeroTrespassStore = ZeroTrespassSuiteState & ZeroTrespassActions;

const INITIAL_DAEMON_METRICS: DaemonProcessMetrics = {
  pid: 41820,
  cpuUsagePercent: 0.4,
  memoryUsageMb: 58.2,
  networkTxKb: 14.8,
  uptimeSeconds: 3600,
  isZombieCleaned: false,
};

const INITIAL_BUDGET: CostBudgetGateConfig = {
  estimatedTokens: 32000,
  estimatedCostUsd: 0.16,
  thresholdUsd: 0.50, // 超过 $0.50 触发高消耗确认闸门
  isGateConfirmed: true,
  actualTokensUsed: 12400,
  actualCostUsd: 0.062,
};

const INITIAL_TELEMETRY: AntiDowngradeTelemetry = {
  physicalModelId: 'claude-3-5-sonnet-20241022',
  claimedModelId: 'claude-3-5-sonnet-20241022',
  provider: 'Anthropic Direct (US-East)',
  latencyMs: 380,
  isDowngradeDetected: false,
};

const INITIAL_STEPSAVER: StepSaverMetrics = {
  savedSteps: [
    '自动跨 3 个业务系统提取合同数据',
    '完成 45 行公式对齐与财务损益测算',
    '生成结构化 Markdown 交付排版',
  ],
  estimatedMinutesSaved: 35,
  honestBoundaryNotice: '当前模型上下文窗口为 200K，已使用 16%；对包含复杂多层合并单元格的 Excel 建议分批导入。',
};

const INITIAL_OTA: MicroDeltaOtaInfo = {
  patchSizeKb: 48,
  fullPackageSizeMb: 420,
  bandwidthSavedPercent: 99.98,
  versionTag: 'v2026.10.15-patch3',
  status: 'ready_to_apply',
};

const INITIAL_STATE: ZeroTrespassSuiteState = {
  autostartAuth: 'denied', // 严禁默认自启，必须显式授权
  neverOverrideSystemChoice: true,
  daemonMetrics: INITIAL_DAEMON_METRICS,
  costBudget: INITIAL_BUDGET,
  physicalTelemetry: INITIAL_TELEMETRY,
  stepSaver: INITIAL_STEPSAVER,
  deltaOta: INITIAL_OTA,
  isByokActive: false,
};

export const useZeroTrespassStore = create<ZeroTrespassStore>((set, get) => ({
  ...INITIAL_STATE,

  setAutostartAuth: (auth: AutostartAuthorizationState) => {
    set({
      autostartAuth: auth,
      neverOverrideSystemChoice: true, // 用户一旦设定，系统启动时绝对不覆盖
    });
  },

  updateDaemonMetrics: (partial: Partial<DaemonProcessMetrics>) => {
    set((state) => ({
      daemonMetrics: {
        ...state.daemonMetrics,
        ...partial,
      },
    }));
  },

  killAndCleanZombieProcess: () => {
    set((state) => ({
      daemonMetrics: {
        ...state.daemonMetrics,
        cpuUsagePercent: 0,
        memoryUsageMb: 0,
        networkTxKb: 0,
        isZombieCleaned: true,
      },
    }));
  },

  setBudgetEstimation: (estimatedTokens: number, estimatedCostUsd: number) => {
    const { costBudget } = get();
    const needsGate = estimatedCostUsd >= costBudget.thresholdUsd;

    set({
      costBudget: {
        ...costBudget,
        estimatedTokens,
        estimatedCostUsd,
        isGateConfirmed: !needsGate, // 高消耗时需要手动确认
      },
    });
  },

  confirmBudgetGate: () => {
    set((state) => ({
      costBudget: {
        ...state.costBudget,
        isGateConfirmed: true,
      },
    }));
  },

  recordTelemetry: (telemetry: Omit<AntiDowngradeTelemetry, 'isDowngradeDetected'>) => {
    const isDowngradeDetected = telemetry.physicalModelId !== telemetry.claimedModelId;

    set({
      physicalTelemetry: {
        ...telemetry,
        isDowngradeDetected,
      },
    });
  },

  recordStepSaver: (metrics: StepSaverMetrics) => {
    set({ stepSaver: metrics });
  },

  updateDeltaOtaStatus: (partial: Partial<MicroDeltaOtaInfo>) => {
    set((state) => ({
      deltaOta: {
        ...state.deltaOta,
        ...partial,
      },
    }));
  },

  toggleByok: (active?: boolean) => {
    set((state) => ({
      isByokActive: active !== undefined ? active : !state.isByokActive,
    }));
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
