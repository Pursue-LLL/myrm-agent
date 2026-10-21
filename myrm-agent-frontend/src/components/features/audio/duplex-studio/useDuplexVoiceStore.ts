import { create } from 'zustand';
import {
  AudioChannelMetrics,
  BargeInState,
  DuplexSettings,
  DuplexVoiceState,
  DuplexTurnMessage,
} from './duplexVoiceTypes';
import {
  finalizeInterruptedTurn,
  healContextOnBargeIn,
  shouldTriggerBargeIn,
} from './duplexVoiceEngine';

export interface DuplexVoiceActions {
  startDuplexSession: () => void;
  stopDuplexSession: () => void;
  feedMicAudioVolume: (volume: number) => void;
  triggerBargeIn: (userSpeechSnippet?: string) => void;
  feedAgentSpeechStream: (chunk: string, isDone?: boolean) => void;
  feedUserSpeechStream: (text: string, isFinal?: boolean) => void;
  dismissBargeInBanner: () => void;
  updateSettings: (partial: Partial<DuplexSettings>) => void;
  clearHistory: () => void;
  reset: () => void;
}

export type DuplexVoiceStore = DuplexVoiceState & DuplexVoiceActions;

const initialSettings: DuplexSettings = {
  vadSilenceThresholdMs: 300,
  bargeInSensitivity: 'medium',
  noiseSuppressionEnabled: true,
  handsFreeAutoStart: false,
};

const initialMetrics: AudioChannelMetrics = {
  micVolume: 0,
  agentVolume: 0,
  noiseFloorDb: -52,
  vadActive: false,
};

const initialState: DuplexVoiceState = {
  status: 'idle',
  metrics: initialMetrics,
  messages: [],
  currentAgentSpeech: '',
  currentUserSpeech: '',
  bargeInState: null,
  settings: initialSettings,
};

export const useDuplexVoiceStore = create<DuplexVoiceStore>((set, get) => ({
  ...initialState,

  startDuplexSession: () => {
    set({
      status: 'listening',
      metrics: {
        ...get().metrics,
        vadActive: false,
      },
    });
  },

  stopDuplexSession: () => {
    set({
      status: 'idle',
      currentAgentSpeech: '',
      currentUserSpeech: '',
      metrics: initialMetrics,
    });
  },

  feedMicAudioVolume: (volume: number) => {
    const { status, settings } = get();
    const clampedVolume = Math.max(0, Math.min(100, volume));
    const isVadActive = clampedVolume >= 18;

    set((state) => ({
      metrics: {
        ...state.metrics,
        micVolume: clampedVolume,
        vadActive: isVadActive,
      },
    }));

    // 随时插话打断检测
    if (shouldTriggerBargeIn(status, clampedVolume, settings.bargeInSensitivity)) {
      get().triggerBargeIn('（检测到用户开口插话）');
    }
  },

  triggerBargeIn: (userSpeechSnippet = '用户开口插话') => {
    const { currentAgentSpeech } = get();

    // 毫秒级自愈截断当前 Agent 播报
    const bargeIn = healContextOnBargeIn(
      currentAgentSpeech,
      userSpeechSnippet,
      currentAgentSpeech.length
    );

    set({
      status: 'interrupted',
      bargeInState: bargeIn,
      currentAgentSpeech: '',
    });

    // 切换至倾听状态以捕获用户的最新纠偏话语
    setTimeout(() => {
      set({ status: 'listening' });
    }, 150);
  },

  feedAgentSpeechStream: (chunk: string, isDone = false) => {
    const nextSpeech = `${get().currentAgentSpeech}${chunk}`;

    if (!isDone) {
      set({
        status: 'speaking',
        currentAgentSpeech: nextSpeech,
        metrics: {
          ...get().metrics,
          agentVolume: Math.min(95, 30 + Math.random() * 50),
        },
      });
      return;
    }

    const newMessage: DuplexTurnMessage = {
      id: `msg-agent-${Date.now()}`,
      role: 'agent',
      content: nextSpeech,
      timestamp: Date.now(),
    };

    set((state) => ({
      status: 'listening',
      currentAgentSpeech: '',
      messages: [...state.messages, newMessage],
      metrics: {
        ...state.metrics,
        agentVolume: 0,
      },
    }));
  },

  feedUserSpeechStream: (text: string, isFinal = false) => {
    const { bargeInState, messages } = get();

    if (!isFinal) {
      set({
        status: 'listening',
        currentUserSpeech: text,
      });
      return;
    }

    // 如果之前发生过打断，将打断沉淀写入历史消息
    let nextMessages = [...messages];
    if (bargeInState?.active) {
      nextMessages = finalizeInterruptedTurn(
        messages,
        bargeInState.interruptedAgentMessage,
        text
      );
    } else {
      nextMessages.push({
        id: `msg-user-${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: Date.now(),
      });
    }

    set({
      status: 'processing',
      currentUserSpeech: '',
      messages: nextMessages,
      bargeInState: bargeInState ? { ...bargeInState, active: false } : null,
    });
  },

  dismissBargeInBanner: () => {
    set({ bargeInState: null });
  },

  updateSettings: (partial) => {
    set((state) => ({
      settings: {
        ...state.settings,
        ...partial,
      },
    }));
  },

  clearHistory: () => {
    set({
      messages: [],
      currentAgentSpeech: '',
      currentUserSpeech: '',
      bargeInState: null,
    });
  },

  reset: () => {
    set(initialState);
  },
}));
