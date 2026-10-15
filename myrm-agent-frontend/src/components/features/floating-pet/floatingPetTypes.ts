/**
 * 桌面端常驻悬浮挂件与即时语音交互套件类型定义
 */

export type PetMoodState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'working'
  | 'celebrating'
  | 'sleeping';

export type PetDockPosition =
  | 'right_edge'
  | 'left_edge'
  | 'bottom_right'
  | 'custom';

export interface PetTaskItem {
  id: string;
  title: string;
  status: 'running' | 'completed' | 'failed';
  progress: number;
  summary: string;
  createdAt: number;
  completedAt?: number;
}

export interface FloatingPetState {
  mood: PetMoodState;
  position: PetDockPosition;
  isPinned: boolean;
  isVoiceRecording: boolean;
  voiceDurationSec: number;
  activeTask: PetTaskItem | null;
  recentTasks: PetTaskItem[];
  isBubbleExpanded: boolean;
  lastVoiceTranscript: string;
}
