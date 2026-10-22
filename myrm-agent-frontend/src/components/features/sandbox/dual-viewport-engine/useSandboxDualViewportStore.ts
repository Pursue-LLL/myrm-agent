import { create } from 'zustand';
import type {
  ConsoleErrorEntry,
  DesignSystemAsset,
  DualViewportMode,
  NetworkAnomalyEntry,
  SandboxDualViewportState,
  SelfHealingCycle,
} from './sandboxDualViewportTypes';

interface SandboxDualViewportActions {
  setActiveMode: (mode: DualViewportMode) => void;
  setTargetPreviewUrl: (url: string) => void;
  addConsoleLog: (entry: Omit<ConsoleErrorEntry, 'id' | 'timestamp'>) => void;
  clearConsoleLogs: () => void;
  addNetworkAnomaly: (entry: Omit<NetworkAnomalyEntry, 'id' | 'timestamp'>) => void;
  clearNetworkAnomalies: () => void;
  registerDesignAssets: (assets: DesignSystemAsset[]) => void;
  toggleAssetEnforcement: (assetId: string) => void;
  triggerSelfHealing: () => void;
  advanceHealingIteration: () => void;
  markHealingSuccess: () => void;
  resetState: () => void;
}

export type SandboxDualViewportStore = SandboxDualViewportState & SandboxDualViewportActions;

const DEFAULT_DESIGN_ASSETS: DesignSystemAsset[] = [
  {
    id: 'ds-table',
    name: 'StandardDataTable',
    category: 'component',
    importPath: '@/components/ui/table',
    description: '带排序、分页与骨架屏的原生表格组件，禁止裸写原生 table',
    isEnforced: true,
  },
  {
    id: 'ds-dialog',
    name: 'AccessibleModalDialog',
    category: 'component',
    importPath: '@/components/ui/dialog',
    description: '支持 Focus Trap 与原生 a11y 的模态对话框',
    isEnforced: true,
  },
  {
    id: 'ds-request',
    name: 'unifiedApiClient',
    category: 'api',
    importPath: '@/lib/api/client',
    description: '全局鉴权拦截与自动退避重试请求客户端，禁止裸用 fetch',
    isEnforced: true,
  },
];

const INITIAL_CYCLE: SelfHealingCycle = {
  cycleId: 'cycle-init',
  iteration: 0,
  maxIterations: 3,
  status: 'idle',
  detectedErrorsCount: 0,
  startedAt: Date.now(),
};

const INITIAL_STATE: SandboxDualViewportState = {
  activeMode: 'desktop',
  targetPreviewUrl: 'http://localhost:5173/preview',
  consoleErrors: [],
  networkAnomalies: [],
  designAssets: DEFAULT_DESIGN_ASSETS,
  healingCycle: INITIAL_CYCLE,
  isLiveReloading: false,
};

export const useSandboxDualViewportStore = create<SandboxDualViewportStore>((set, get) => ({
  ...INITIAL_STATE,

  setActiveMode: (mode: DualViewportMode) => {
    set({ activeMode: mode });
  },

  setTargetPreviewUrl: (url: string) => {
    set({ targetPreviewUrl: url });
  },

  addConsoleLog: (entry: Omit<ConsoleErrorEntry, 'id' | 'timestamp'>) => {
    const newEntry: ConsoleErrorEntry = {
      ...entry,
      id: `err-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: Date.now(),
    };

    set((state) => ({
      consoleErrors: [newEntry, ...state.consoleErrors].slice(0, 50),
    }));
  },

  clearConsoleLogs: () => {
    set({ consoleErrors: [] });
  },

  addNetworkAnomaly: (entry: Omit<NetworkAnomalyEntry, 'id' | 'timestamp'>) => {
    const newEntry: NetworkAnomalyEntry = {
      ...entry,
      id: `net-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: Date.now(),
    };

    set((state) => ({
      networkAnomalies: [newEntry, ...state.networkAnomalies].slice(0, 50),
    }));
  },

  clearNetworkAnomalies: () => {
    set({ networkAnomalies: [] });
  },

  registerDesignAssets: (assets: DesignSystemAsset[]) => {
    set({ designAssets: assets });
  },

  toggleAssetEnforcement: (assetId: string) => {
    set((state) => ({
      designAssets: state.designAssets.map((asset) => {
        if (asset.id === assetId) {
          return { ...asset, isEnforced: !asset.isEnforced };
        }
        return asset;
      }),
    }));
  },

  triggerSelfHealing: () => {
    const { consoleErrors, networkAnomalies, healingCycle } = get();
    const errorCount = consoleErrors.length + networkAnomalies.length;

    if (errorCount === 0) {
      set({
        healingCycle: {
          ...healingCycle,
          status: 'healed_verified',
          detectedErrorsCount: 0,
          resolvedAt: Date.now(),
        },
      });
      return;
    }

    const firstError = consoleErrors[0]?.message ?? `${networkAnomalies[0]?.status} ${networkAnomalies[0]?.url}`;

    set({
      healingCycle: {
        cycleId: `cycle-${Date.now()}`,
        iteration: 1,
        maxIterations: 3,
        status: 'healing_prompt_injected',
        detectedErrorsCount: errorCount,
        lastErrorSummary: firstError,
        startedAt: Date.now(),
      },
    });
  },

  advanceHealingIteration: () => {
    const { healingCycle } = get();
    const nextIteration = healingCycle.iteration + 1;

    if (nextIteration > healingCycle.maxIterations) {
      set({
        healingCycle: {
          ...healingCycle,
          status: 'healing_exhausted',
        },
      });
      return;
    }

    set({
      healingCycle: {
        ...healingCycle,
        iteration: nextIteration,
        status: 'recompiling',
      },
    });
  },

  markHealingSuccess: () => {
    set((state) => ({
      consoleErrors: [],
      networkAnomalies: [],
      healingCycle: {
        ...state.healingCycle,
        status: 'healed_verified',
        detectedErrorsCount: 0,
        resolvedAt: Date.now(),
      },
    }));
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
