export type SkeuomorphicSkinType =
  | 'classic_ipod'
  | 'polaroid_album'
  | 'retro_typewriter'
  | 'vintage_flip_clock';

export type ArtifactCategory = 'code' | 'design' | 'doc' | 'preview' | 'media';

export type TaskRunStatus = 'completed' | 'in_progress' | 'failed' | 'paused';

export interface ArtifactPlayItem {
  id: string;
  taskTitle: string;
  stageName: string;
  createdAt: string;
  status: TaskRunStatus;
  summary: string;
  artifactType: ArtifactCategory;
  previewUrl?: string;
  tokensUsed: number;
  durationMs: number;
  authorAgent: string;
  codeSnippet?: string;
}

export interface WheelGestureState {
  angle: number;
  previousAngle: number;
  activeStep: number;
  totalSteps: number;
  isDragging: boolean;
  tickCount: number;
}

export interface SynthAudioConfig {
  soundEnabled: boolean;
  volume: number;
  hapticEnabled: boolean;
}

export interface SkeuomorphicAppConfig {
  activeSkin: SkeuomorphicSkinType;
  audioConfig: SynthAudioConfig;
  autoPlay: boolean;
  autoPlayIntervalMs: number;
  isMinimized: boolean;
  activeItemIndex: number;
}
