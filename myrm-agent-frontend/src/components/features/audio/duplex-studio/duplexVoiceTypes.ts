export type DuplexSessionStatus =
  | 'idle'
  | 'listening'
  | 'speaking'
  | 'interrupted'
  | 'processing';

export type BargeInSensitivity = 'low' | 'medium' | 'high';

export interface BargeInState {
  active: boolean;
  interruptedAt: number;
  interruptedAgentMessage: string;
  userInterruptionSnippet: string;
  healedContextPreview: string;
}

export interface AudioChannelMetrics {
  micVolume: number;
  agentVolume: number;
  noiseFloorDb: number;
  vadActive: boolean;
}

export interface DuplexTurnMessage {
  id: string;
  role: 'user' | 'agent';
  content: string;
  wasInterrupted?: boolean;
  interruptedAtPosition?: number;
  timestamp: number;
}

export interface DuplexSettings {
  vadSilenceThresholdMs: number;
  bargeInSensitivity: BargeInSensitivity;
  noiseSuppressionEnabled: boolean;
  handsFreeAutoStart: boolean;
}

export interface DuplexVoiceState {
  status: DuplexSessionStatus;
  metrics: AudioChannelMetrics;
  messages: DuplexTurnMessage[];
  currentAgentSpeech: string;
  currentUserSpeech: string;
  bargeInState: BargeInState | null;
  settings: DuplexSettings;
}
