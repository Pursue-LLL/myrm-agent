import {
  PetDockPosition,
  PetMoodState,
  PetTaskItem,
} from './floatingPetTypes';

export function computePetMood(
  isVoiceRecording: boolean,
  activeTask: PetTaskItem | null
): PetMoodState {
  if (isVoiceRecording) {
    return 'listening';
  }

  if (activeTask) {
    if (activeTask.status === 'running') {
      if (activeTask.progress < 20) {
        return 'thinking';
      }
      return 'working';
    }
    if (activeTask.status === 'completed') {
      return 'celebrating';
    }
  }

  return 'idle';
}

export interface PetGlowStyle {
  ringColor: string;
  pulseClass: string;
  badgeBg: string;
  badgeText: string;
  statusLabel: string;
}

export function getPetGlowStyle(mood: PetMoodState): PetGlowStyle {
  if (mood === 'listening') {
    return {
      ringColor: 'border-red-500 shadow-[0_0_16px_rgba(239,68,68,0.7)]',
      pulseClass: 'animate-ping',
      badgeBg: 'bg-red-500/20',
      badgeText: 'text-red-300 border-red-500/40',
      statusLabel: '倾听语音指令中...',
    };
  }

  if (mood === 'thinking') {
    return {
      ringColor: 'border-purple-500 shadow-[0_0_16px_rgba(168,85,247,0.6)]',
      pulseClass: 'animate-pulse',
      badgeBg: 'bg-purple-500/20',
      badgeText: 'text-purple-300 border-purple-500/40',
      statusLabel: '深度推理意图...',
    };
  }

  if (mood === 'working') {
    return {
      ringColor: 'border-cyan-500 shadow-[0_0_16px_rgba(6,182,212,0.6)]',
      pulseClass: 'animate-spin',
      badgeBg: 'bg-cyan-500/20',
      badgeText: 'text-cyan-300 border-cyan-500/40',
      statusLabel: '后台自主执行中',
    };
  }

  if (mood === 'celebrating') {
    return {
      ringColor: 'border-amber-400 shadow-[0_0_18px_rgba(251,191,36,0.8)]',
      pulseClass: 'animate-bounce',
      badgeBg: 'bg-amber-500/20',
      badgeText: 'text-amber-300 border-amber-500/40',
      statusLabel: '任务顺利达成！',
    };
  }

  return {
    ringColor: 'border-zinc-700 shadow-[0_0_8px_rgba(255,255,255,0.05)]',
    pulseClass: '',
    badgeBg: 'bg-zinc-800',
    badgeText: 'text-zinc-400 border-zinc-700',
    statusLabel: '静默陪伴中',
  };
}

export function formatVoiceTranscriptToTask(transcript: string): PetTaskItem {
  const clean = transcript.trim();
  const title = clean.length > 24 ? `${clean.substring(0, 24)}...` : clean;

  return {
    id: `pet-task-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
    title: title || '未命名语音快捷任务',
    status: 'running',
    progress: 10,
    summary: clean,
    createdAt: Date.now(),
  };
}

export function calculateDockPositionClasses(position: PetDockPosition): string {
  if (position === 'left_edge') {
    return 'left-4 top-1/2 -translate-y-1/2';
  }
  if (position === 'bottom_right') {
    return 'right-6 bottom-6';
  }
  // 默认贴在屏幕右边缘中间偏下
  return 'right-4 top-1/2 -translate-y-1/2';
}
