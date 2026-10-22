import { create } from 'zustand';
import {
  FloatingPetState,
  PetDockPosition,
  PetMoodState,
  PetTaskItem,
} from './floatingPetTypes';
import {
  computePetMood,
  formatVoiceTranscriptToTask,
} from './floatingPetEngine';

export interface FloatingPetActions {
  startPushToTalk: () => void;
  stopPushToTalk: (transcript?: string) => PetTaskItem | null;
  updateTaskProgress: (
    taskId: string,
    progress: number,
    status?: 'running' | 'completed' | 'failed'
  ) => void;
  toggleBubbleExpanded: (expanded?: boolean) => void;
  setDockPosition: (position: PetDockPosition) => void;
  setPinned: (pinned: boolean) => void;
  clearActiveTask: () => void;
  reset: () => void;
}

export type FloatingPetStore = FloatingPetState & FloatingPetActions;

const INITIAL_STATE: FloatingPetState = {
  mood: 'idle',
  position: 'right_edge',
  isPinned: false,
  isVoiceRecording: false,
  voiceDurationSec: 0,
  activeTask: null,
  recentTasks: [],
  isBubbleExpanded: false,
  lastVoiceTranscript: '',
};

export const useFloatingPetStore = create<FloatingPetStore>((set, get) => ({
  ...INITIAL_STATE,

  startPushToTalk: () => {
    set({
      isVoiceRecording: true,
      voiceDurationSec: 0,
      mood: 'listening',
      isBubbleExpanded: false,
    });
  },

  stopPushToTalk: (transcript?: string) => {
    const raw = transcript?.trim() || get().lastVoiceTranscript;
    set({ isVoiceRecording: false });

    if (!raw) {
      const mood = computePetMood(false, get().activeTask);
      set({ mood });
      return null;
    }

    const newTask = formatVoiceTranscriptToTask(raw);
    const newMood: PetMoodState = 'thinking';

    set({
      activeTask: newTask,
      lastVoiceTranscript: raw,
      mood: newMood,
      isBubbleExpanded: true,
    });

    return newTask;
  },

  updateTaskProgress: (
    taskId: string,
    progress: number,
    status: 'running' | 'completed' | 'failed' = 'running'
  ) => {
    const { activeTask, recentTasks } = get();
    if (!activeTask || activeTask.id !== taskId) {
      return;
    }

    const updatedTask: PetTaskItem = {
      ...activeTask,
      progress: Math.min(100, Math.max(0, progress)),
      status,
      completedAt: status === 'completed' ? Date.now() : activeTask.completedAt,
    };

    const nextMood = computePetMood(get().isVoiceRecording, updatedTask);

    if (status === 'completed' || status === 'failed') {
      set({
        activeTask: updatedTask,
        recentTasks: [updatedTask, ...recentTasks.slice(0, 9)],
        mood: nextMood,
      });
      return;
    }

    set({
      activeTask: updatedTask,
      mood: nextMood,
    });
  },

  toggleBubbleExpanded: (expanded?: boolean) => {
    set((state) => ({
      isBubbleExpanded: expanded !== undefined ? expanded : !state.isBubbleExpanded,
    }));
  },

  setDockPosition: (position: PetDockPosition) => {
    set({ position });
  },

  setPinned: (pinned: boolean) => {
    set({ isPinned: pinned });
  },

  clearActiveTask: () => {
    const { activeTask, recentTasks } = get();
    const updatedRecent = activeTask ? [activeTask, ...recentTasks.slice(0, 9)] : recentTasks;
    set({
      activeTask: null,
      recentTasks: updatedRecent,
      mood: 'idle',
      isBubbleExpanded: false,
    });
  },

  reset: () => {
    set(INITIAL_STATE);
  },
}));
