import { create } from 'zustand';
import type {
  AgentWaveformState,
  ErgonomicCockpitState,
  InlineAgentPersona,
  TaskGaitProgress,
  ViewportMode,
} from './ergonomicCockpitTypes';

interface ErgonomicCockpitActions {
  setViewportMode: (mode: ViewportMode) => void;
  setAgentWaveformState: (state: AgentWaveformState) => void;
  updateTaskGaitProgress: (progress: Partial<TaskGaitProgress> | null) => void;
  toggleSidePanels: (collapsed?: boolean) => void;
  setActivePersona: (persona: Partial<InlineAgentPersona>) => void;
  resetState: () => void;
}

export type ErgonomicCockpitStore = ErgonomicCockpitState & ErgonomicCockpitActions;

const DEFAULT_PERSONA: InlineAgentPersona = {
  agentId: 'agent-core-architect',
  name: '首席全栈架构师',
  role: '技术方案审查与系统重构',
  avatarIconName: 'Bot',
  baseModel: 'claude-3-5-sonnet',
  state: 'thinking',
};

const DEFAULT_GAIT: TaskGaitProgress = {
  taskId: 'task-refactor-99',
  agentId: 'agent-core-architect',
  currentStep: 3,
  totalSteps: 5,
  stepTitle: '正在执行宽屏中轴视界人体工效学向心重构与步态解耦...',
  percentage: 60,
  isDecoupledFromInput: true,
};

const INITIAL_STATE: ErgonomicCockpitState = {
  viewportMode: 'wide_ergonomic',
  isSidePanelsCollapsed: false,
  activePersona: DEFAULT_PERSONA,
  currentGait: DEFAULT_GAIT,
};

export const useErgonomicCockpitStore = create<ErgonomicCockpitStore>((set, get) => ({
  ...INITIAL_STATE,

  setViewportMode: (mode: ViewportMode) => {
    set({ viewportMode: mode });
  },

  setAgentWaveformState: (state: AgentWaveformState) => {
    set((prev) => ({
      activePersona: {
        ...prev.activePersona,
        state,
      },
    }));
  },

  updateTaskGaitProgress: (progress: Partial<TaskGaitProgress> | null) => {
    if (progress === null) {
      set({ currentGait: null });
      return;
    }

    set((prev) => ({
      currentGait: {
        taskId: progress.taskId ?? prev.currentGait?.taskId ?? `task-${Date.now()}`,
        agentId: progress.agentId ?? prev.currentGait?.agentId ?? prev.activePersona.agentId,
        currentStep: progress.currentStep ?? prev.currentGait?.currentStep ?? 1,
        totalSteps: progress.totalSteps ?? prev.currentGait?.totalSteps ?? 1,
        stepTitle: progress.stepTitle ?? prev.currentGait?.stepTitle ?? '执行中...',
        percentage: progress.percentage ?? prev.currentGait?.percentage ?? 0,
        isDecoupledFromInput: true, // 核心保证始终与输入框解耦
      },
    }));
  },

  toggleSidePanels: (collapsed?: boolean) => {
    set((state) => ({
      isSidePanelsCollapsed:
        collapsed !== undefined ? collapsed : !state.isSidePanelsCollapsed,
    }));
  },

  setActivePersona: (personaUpdate: Partial<InlineAgentPersona>) => {
    set((state) => ({
      activePersona: {
        ...state.activePersona,
        ...personaUpdate,
      },
    }));
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
