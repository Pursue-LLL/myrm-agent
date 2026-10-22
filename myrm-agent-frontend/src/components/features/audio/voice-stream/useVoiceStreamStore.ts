/**
 * Voice Stream Zustand Store
 * Web 端全双工语音交互流状态机与安全策略恢复调度
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import { create } from 'zustand';
import {
  DEFAULT_AUDIO_CONFIG,
  FrontendVadStateMachine,
  processAudioInputChunk,
} from './audioPcmProcessor';
import {
  detectAudioEnvironment,
} from './secureAudioContextDetector';
import {
  PcmAudioFrame,
  SecureAudioEnvironmentReport,
  VadState,
  VoiceStreamMetrics,
  VoiceStreamStatus,
} from './voiceStreamTypes';

interface VoiceStreamStoreState {
  status: VoiceStreamStatus;
  environmentReport: SecureAudioEnvironmentReport;
  metrics: VoiceStreamMetrics;
  vadState: VadState;
  vadThreshold: number;
  recentFrames: PcmAudioFrame[];
  isDuplexEnabled: boolean;
  isAutoplayDismissed: boolean;
  errorMessage: string | null;

  // Actions
  refreshEnvironmentReport: (customEnv?: {
    isSecureContext?: boolean;
    protocol?: string;
    host?: string;
    hasMediaDevices?: boolean;
    audioContextState?: AudioContextState;
  }) => void;
  resumeContext: () => void;
  startDuplexStream: () => Promise<boolean>;
  stopStream: () => void;
  processAudioChunk: (float32Chunk: Float32Array) => PcmAudioFrame;
  setVadThreshold: (threshold: number) => void;
  setIsDuplexEnabled: (enabled: boolean) => void;
  simulateAgentSpeech: (isSpeaking: boolean) => void;
  resetToDefault: () => void;
}

const vadMachine = new FrontendVadStateMachine(DEFAULT_AUDIO_CONFIG.vadThreshold);

const INITIAL_METRICS: VoiceStreamMetrics = {
  currentRms: 0,
  peakRms: 0,
  decibel: -100,
  framesSent: 0,
  framesReceived: 0,
  latencyMs: 38,
  packetLossRate: 0,
};

export const useVoiceStreamStore = create<VoiceStreamStoreState>((set, get) => ({
  status: 'idle',
  environmentReport: detectAudioEnvironment(),
  metrics: { ...INITIAL_METRICS },
  vadState: 'silence',
  vadThreshold: DEFAULT_AUDIO_CONFIG.vadThreshold,
  recentFrames: [],
  isDuplexEnabled: false,
  isAutoplayDismissed: false,
  errorMessage: null,

  refreshEnvironmentReport: (customEnv) => {
    const report = detectAudioEnvironment(customEnv);
    set({ environmentReport: report });
  },

  resumeContext: () => {
    set((state) => ({
      isAutoplayDismissed: true,
      environmentReport: {
        ...state.environmentReport,
        isAutoplaySuspended: false,
        requiresUserGesture: false,
      },
    }));
  },

  startDuplexStream: async () => {
    const report = get().environmentReport;

    if (!report.isSecureContext) {
      set({
        status: 'error',
        errorMessage: '无法启动麦克风录音：当前运行环境属于非安全上下文 (Insecure Context)',
      });
      return false;
    }

    if (!report.hasGetUserMedia) {
      set({
        status: 'error',
        errorMessage: '浏览器未提供 getUserMedia 麦克风录音接口',
      });
      return false;
    }

    vadMachine.reset();
    set({
      status: 'duplex_active',
      isDuplexEnabled: true,
      errorMessage: null,
      vadState: 'silence',
    });
    return true;
  },

  stopStream: () => {
    vadMachine.reset();
    set({
      status: 'idle',
      isDuplexEnabled: false,
      vadState: 'silence',
      metrics: {
        ...get().metrics,
        currentRms: 0,
        decibel: -100,
      },
    });
  },

  processAudioChunk: (float32Chunk: Float32Array) => {
    const frame = processAudioInputChunk(float32Chunk, vadMachine);
    const state = get();

    const currentPeak = Math.max(state.metrics.peakRms, frame.rmsEnergy);
    const updatedMetrics: VoiceStreamMetrics = {
      ...state.metrics,
      currentRms: frame.rmsEnergy,
      peakRms: currentPeak,
      decibel: frame.decibel,
      framesSent: state.metrics.framesSent + 1,
    };

    const nextFrames = [frame, ...state.recentFrames.slice(0, 19)];

    set({
      metrics: updatedMetrics,
      vadState: frame.isSpeech ? 'speech' : 'silence',
      recentFrames: nextFrames,
    });

    return frame;
  },

  setVadThreshold: (threshold: number) => {
    vadMachine.setThreshold(threshold);
    set({ vadThreshold: threshold });
  },

  setIsDuplexEnabled: (enabled: boolean) => {
    set({ isDuplexEnabled: enabled });
  },

  simulateAgentSpeech: (isSpeaking: boolean) => {
    set((state) => {
      if (isSpeaking) {
        return {
          status: 'speaking',
          metrics: {
            ...state.metrics,
            framesReceived: state.metrics.framesReceived + 1,
          },
        };
      }
      return {
        status: state.isDuplexEnabled ? 'duplex_active' : 'idle',
      };
    });
  },

  resetToDefault: () => {
    vadMachine.reset();
    set({
      status: 'idle',
      environmentReport: detectAudioEnvironment(),
      metrics: { ...INITIAL_METRICS },
      vadState: 'silence',
      vadThreshold: DEFAULT_AUDIO_CONFIG.vadThreshold,
      recentFrames: [],
      isDuplexEnabled: false,
      isAutoplayDismissed: false,
      errorMessage: null,
    });
  },
}));
