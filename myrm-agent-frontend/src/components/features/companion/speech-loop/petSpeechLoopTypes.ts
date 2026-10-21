export type LoopPhase =
  | 'idle'
  | 'listening'
  | 'planning'
  | 'coding'
  | 'executing'
  | 'reviewing'
  | 'completed';

export type PetMood =
  | 'calm'
  | 'listening'
  | 'thinking'
  | 'coding'
  | 'celebrating'
  | 'alert';

export type VoiceCaptureStatus =
  | 'inactive'
  | 'listening'
  | 'processing'
  | 'error';

export type StepStatus = 'pending' | 'running' | 'completed' | 'failed';

export type FourStagePhase = 'plan' | 'code' | 'exec' | 'verify';

export interface LoopTaskStep {
  id: string;
  stage: FourStagePhase;
  title: string;
  detail: string;
  status: StepStatus;
  durationMs?: number;
}

export interface ApprovalAction {
  id: string;
  summary: string;
  riskLevel: 'low' | 'medium' | 'high';
  proposedFiles: string[];
  status: 'pending' | 'approved' | 'rejected';
}

export interface VoiceTranscriptionEvent {
  text: string;
  isFinal: boolean;
  confidence: number;
}

export interface PetSpeechLoopState {
  currentPhase: LoopPhase;
  voiceStatus: VoiceCaptureStatus;
  transcript: string;
  interimTranscript: string;
  steps: LoopTaskStep[];
  approvalAction: ApprovalAction | null;
  isApprovalDrawerOpen: boolean;
  petMood: PetMood;
  bubbleMessage: string | null;
  isWiggling: boolean;
}
