/**
 * Voice Stream & Audio Resilience Types
 * Web 端全双工语音交互流、安全上下文检测与 Autoplay 弹性恢复类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 规范定义音频采样、VAD 状态机与安全策略报告；
 * 3. 行数严格受控在 400 行以内。
 */

export type VoiceStreamStatus =
  | 'idle'
  | 'requesting_permission'
  | 'listening'
  | 'speaking'
  | 'duplex_active'
  | 'suspended'
  | 'error';

export type VadState = 'speech' | 'silence';

export interface SecureAudioEnvironmentReport {
  isSecureContext: boolean;
  protocol: string;
  host: string;
  isLocalhost: boolean;
  isLanIp: boolean;
  hasGetUserMedia: boolean;
  isAutoplaySuspended: boolean;
  requiresUserGesture: boolean;
  canRecord: boolean;
  warnings: string[];
  remedyGuides: string[];
}

export interface AudioSampleConfig {
  sampleRate: number; // e.g. 16000 Hz
  channelCount: number; // e.g. 1 (mono)
  bufferSize: number; // e.g. 2048
  vadThreshold: number; // e.g. 0.015 RMS
}

export interface PcmAudioFrame {
  timestamp: number;
  sampleRate: number;
  pcmData: Int16Array;
  rmsEnergy: number;
  decibel: number;
  isSpeech: boolean;
}

export interface VoiceStreamMetrics {
  currentRms: number;
  peakRms: number;
  decibel: number;
  framesSent: number;
  framesReceived: number;
  latencyMs: number;
  packetLossRate: number;
}
