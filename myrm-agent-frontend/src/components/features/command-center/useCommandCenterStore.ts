import { create } from 'zustand';
import {
  CommandCenterLogEntry,
  CommandCenterTab,
  GatewayHealthState,
  LogComponent,
  MaintenanceActionType,
  MaintenanceTaskState,
  SessionAuditPackPayload,
  SessionSummaryItem,
  UsageHorizon,
  UsageSummary,
} from './commandCenterTypes';
import {
  generateDebugShareBundle,
  generateSessionAuditPack,
  getDefaultHealth,
  getDefaultLogs,
  getDefaultSessions,
  getDefaultUsageSummary,
} from './commandCenterEngine';

interface CommandCenterState {
  isOpen: boolean;
  activeTab: CommandCenterTab;
  searchQuery: string;
  sessions: SessionSummaryItem[];
  health: GatewayHealthState;
  usageHorizon: UsageHorizon;
  usageSummary: UsageSummary;
  logs: CommandCenterLogEntry[];
  selectedLogComponent: LogComponent | 'all';
  maintenanceTask: MaintenanceTaskState;
  exportedAuditPack: SessionAuditPackPayload | null;
  debugSharePayload: string | null;

  openModal: (initialTab?: CommandCenterTab) => void;
  closeModal: () => void;
  setActiveTab: (tab: CommandCenterTab) => void;
  setSearchQuery: (query: string) => void;
  togglePinSession: (sessionId: string) => void;
  exportSessionAuditPack: (sessionId: string) => SessionAuditPackPayload | null;
  setUsageHorizon: (horizon: UsageHorizon) => void;
  setSelectedLogComponent: (component: LogComponent | 'all') => void;
  runMaintenanceAction: (action: MaintenanceActionType) => void;
  generateDebugShare: () => string;
  resetStore: () => void;
}

export const useCommandCenterStore = create<CommandCenterState>((set, get) => ({
  isOpen: false,
  activeTab: 'sessions',
  searchQuery: '',
  sessions: getDefaultSessions(),
  health: getDefaultHealth(),
  usageHorizon: 7,
  usageSummary: getDefaultUsageSummary(7),
  logs: getDefaultLogs(),
  selectedLogComponent: 'all',
  maintenanceTask: {
    action: null,
    status: 'idle',
    message: '',
    progressPercent: 0,
  },
  exportedAuditPack: null,
  debugSharePayload: null,

  openModal: (initialTab = 'sessions') => {
    set({ isOpen: true, activeTab: initialTab });
  },

  closeModal: () => {
    set({ isOpen: false, searchQuery: '' });
  },

  setActiveTab: (tab) => {
    set({ activeTab: tab });
  },

  setSearchQuery: (query) => {
    set({ searchQuery: query });
  },

  togglePinSession: (sessionId) => {
    const updated = get().sessions.map((s) => {
      if (s.id === sessionId) {
        return { ...s, isPinned: !s.isPinned };
      }
      return s;
    });
    set({ sessions: updated });
  },

  exportSessionAuditPack: (sessionId) => {
    const session = get().sessions.find((s) => s.id === sessionId);
    if (!session) {
      return null;
    }
    const pack = generateSessionAuditPack(session);
    set({ exportedAuditPack: pack });
    return pack;
  },

  setUsageHorizon: (horizon) => {
    set({
      usageHorizon: horizon,
      usageSummary: getDefaultUsageSummary(horizon),
    });
  },

  setSelectedLogComponent: (component) => {
    set({ selectedLogComponent: component });
  },

  runMaintenanceAction: (action) => {
    set({
      maintenanceTask: {
        action,
        status: 'running',
        message: `正在执行维护任务: ${action}...`,
        progressPercent: 30,
      },
    });

    // 模拟运维任务完成
    setTimeout(() => {
      set({
        maintenanceTask: {
          action,
          status: 'success',
          message: `维护任务 ${action} 执行完毕，健康状态已确认。`,
          progressPercent: 100,
        },
      });
    }, 50);
  },

  generateDebugShare: () => {
    const { logs, health } = get();
    const bundle = generateDebugShareBundle(logs, health);
    set({ debugSharePayload: bundle });
    return bundle;
  },

  resetStore: () => {
    set({
      isOpen: false,
      activeTab: 'sessions',
      searchQuery: '',
      sessions: getDefaultSessions(),
      health: getDefaultHealth(),
      usageHorizon: 7,
      usageSummary: getDefaultUsageSummary(7),
      logs: getDefaultLogs(),
      selectedLogComponent: 'all',
      maintenanceTask: {
        action: null,
        status: 'idle',
        message: '',
        progressPercent: 0,
      },
      exportedAuditPack: null,
      debugSharePayload: null,
    });
  },
}));
