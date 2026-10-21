/**
 * useDesktopPetPulseStore.ts
 * 桌面常驻灵动悬浮桌宠、状态脉冲与数据迁移状态管理
 */

import { create } from 'zustand';
import type {
  AgentIdentityProjection,
  MigrationReport,
  PetApprovalNotice,
  PetPulseStatus,
  VoiceDirectInputState,
  VoiceTaskDispatchPayload,
} from './desktopPetPulseTypes';
import { formatVoiceDispatchPayload } from './desktopPetPulseEngine';

export interface DesktopPetPulseStoreState {
  petStatus: PetPulseStatus;
  isPaused: boolean;
  activeApproval: PetApprovalNotice | null;
  primaryAgent: AgentIdentityProjection | null;
  allAgents: AgentIdentityProjection[];
  activeQueue: Array<{
    agentId: string;
    status: 'queued' | 'approving' | 'working';
  }>;
  isQuickActionOpen: boolean;
  isVoiceInputActive: boolean;
  voiceState: VoiceDirectInputState;
  isMigrationModalOpen: boolean;
  lastMigrationReport: MigrationReport | null;
  position: { x: number; y: number };
  isTauriMode: boolean;
  mainWindowFocusedCount: number;

  // Actions
  setPetStatus: (status: PetPulseStatus) => void;
  togglePause: () => void;
  setActiveApproval: (approval: PetApprovalNotice | null) => void;
  setPrimaryAgent: (agent: AgentIdentityProjection | null) => void;
  setAllAgents: (agents: AgentIdentityProjection[]) => void;
  enqueueAgent: (
    agentId: string,
    status: 'queued' | 'approving' | 'working'
  ) => void;
  dequeueAgent: (agentId: string) => void;
  toggleQuickAction: (open?: boolean) => void;
  toggleVoiceInput: (active?: boolean) => void;
  updateVoiceState: (partial: Partial<VoiceDirectInputState>) => void;
  toggleMigrationModal: (open?: boolean) => void;
  setLastMigrationReport: (report: MigrationReport | null) => void;
  setPosition: (pos: { x: number; y: number }) => void;
  triggerDirectVoiceDispatch: (
    prompt: string,
    autoRun?: boolean
  ) => VoiceTaskDispatchPayload;
  requestOpenMainWindow: () => void;
  resetAll: () => void;
}

const initialVoiceState: VoiceDirectInputState = {
  isRecording: false,
  isTranscribing: false,
  audioLevel: 0,
  durationMs: 0,
  error: null,
};

export const useDesktopPetPulseStore = create<DesktopPetPulseStoreState>(
  (set, get) => ({
    petStatus: 'idle',
    isPaused: false,
    activeApproval: null,
    primaryAgent: {
      agentId: 'default-assistant',
      name: 'Myrm 灵动助手',
      colorTheme: '#3b82f6',
      activeRole: '通用调度',
      isPrimary: true,
    },
    allAgents: [
      {
        agentId: 'default-assistant',
        name: 'Myrm 灵动助手',
        colorTheme: '#3b82f6',
        activeRole: '通用调度',
        isPrimary: true,
      },
    ],
    activeQueue: [],
    isQuickActionOpen: false,
    isVoiceInputActive: false,
    voiceState: initialVoiceState,
    isMigrationModalOpen: false,
    lastMigrationReport: null,
    position: { x: 32, y: 32 },
    isTauriMode:
      typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window,
    mainWindowFocusedCount: 0,

    setPetStatus: (status: PetPulseStatus): void => {
      set({ petStatus: status });
    },

    togglePause: (): void => {
      set((state) => ({ isPaused: !state.isPaused }));
    },

    setActiveApproval: (approval: PetApprovalNotice | null): void => {
      set({
        activeApproval: approval,
        petStatus: approval !== null ? 'approval_needed' : get().petStatus,
      });
    },

    setPrimaryAgent: (agent: AgentIdentityProjection | null): void => {
      set({ primaryAgent: agent });
    },

    setAllAgents: (agents: AgentIdentityProjection[]): void => {
      set({ allAgents: agents });
    },

    enqueueAgent: (
      agentId: string,
      status: 'queued' | 'approving' | 'working'
    ): void => {
      set((state) => {
        const filtered = state.activeQueue.filter(
          (item) => item.agentId !== agentId
        );
        return {
          activeQueue: [...filtered, { agentId, status }],
        };
      });
    },

    dequeueAgent: (agentId: string): void => {
      set((state) => ({
        activeQueue: state.activeQueue.filter(
          (item) => item.agentId !== agentId
        ),
      }));
    },

    toggleQuickAction: (open?: boolean): void => {
      set((state) => ({
        isQuickActionOpen:
          open !== undefined ? open : !state.isQuickActionOpen,
      }));
    },

    toggleVoiceInput: (active?: boolean): void => {
      set((state) => ({
        isVoiceInputActive:
          active !== undefined ? active : !state.isVoiceInputActive,
      }));
    },

    updateVoiceState: (partial: Partial<VoiceDirectInputState>): void => {
      set((state) => ({
        voiceState: { ...state.voiceState, ...partial },
      }));
    },

    toggleMigrationModal: (open?: boolean): void => {
      set((state) => ({
        isMigrationModalOpen:
          open !== undefined ? open : !state.isMigrationModalOpen,
      }));
    },

    setLastMigrationReport: (report: MigrationReport | null): void => {
      set({ lastMigrationReport: report });
    },

    setPosition: (pos: { x: number; y: number }): void => {
      set({ position: pos });
    },

    triggerDirectVoiceDispatch: (
      prompt: string,
      autoRun = true
    ): VoiceTaskDispatchPayload => {
      const state = get();
      const payload = formatVoiceDispatchPayload(prompt, {
        targetAgentId: state.primaryAgent?.agentId,
        autoRun,
      });
      set({
        petStatus: 'thinking',
        isVoiceInputActive: false,
        voiceState: initialVoiceState,
      });
      return payload;
    },

    requestOpenMainWindow: (): void => {
      set((state) => ({
        mainWindowFocusedCount: state.mainWindowFocusedCount + 1,
      }));
    },

    resetAll: (): void => {
      set({
        petStatus: 'idle',
        isPaused: false,
        activeApproval: null,
        activeQueue: [],
        isQuickActionOpen: false,
        isVoiceInputActive: false,
        voiceState: initialVoiceState,
        isMigrationModalOpen: false,
        lastMigrationReport: null,
      });
    },
  })
);
