import { create } from 'zustand';
import {
  ReadOnlyCodeSnapshot,
  ReadOnlyStepSnapshot,
  SideTrackSession,
} from './sideTrackTypes';
import {
  createSideTrackSession,
  generateLocalExplainerAnswer,
} from './sideTrackEngine';

export interface SideTrackStoreState {
  isDrawerOpen: boolean;
  activeSession: SideTrackSession | null;
  selectedCodeSnapshot: ReadOnlyCodeSnapshot | null;

  // Actions
  openSideTrack: (
    mainSessionId: string,
    mainTaskName: string,
    activeStep?: ReadOnlyStepSnapshot,
    codeSnapshots?: ReadOnlyCodeSnapshot[]
  ) => void;
  closeSideTrack: () => void;
  toggleDrawer: (open?: boolean) => void;
  selectCodeSnapshot: (snapshot: ReadOnlyCodeSnapshot | null) => void;
  sendInquiry: (query: string) => void;
  clearSession: () => void;
}

export const useSideTrackStore = create<SideTrackStoreState>((set, get) => ({
  isDrawerOpen: false,
  activeSession: null,
  selectedCodeSnapshot: null,

  openSideTrack: (
    mainSessionId: string,
    mainTaskName: string,
    activeStep?: ReadOnlyStepSnapshot,
    codeSnapshots: ReadOnlyCodeSnapshot[] = []
  ) => {
    const session = createSideTrackSession(
      mainSessionId,
      mainTaskName,
      activeStep,
      codeSnapshots
    );
    const initialCode = codeSnapshots.length > 0 ? codeSnapshots[0] : null;

    set({
      activeSession: session,
      isDrawerOpen: true,
      selectedCodeSnapshot: initialCode,
    });
  },

  closeSideTrack: () => {
    set({ isDrawerOpen: false });
  },

  toggleDrawer: (open?: boolean) => {
    set((state) => ({
      isDrawerOpen: typeof open === 'boolean' ? open : !state.isDrawerOpen,
    }));
  },

  selectCodeSnapshot: (snapshot: ReadOnlyCodeSnapshot | null) => {
    set({ selectedCodeSnapshot: snapshot });
  },

  sendInquiry: (query: string) => {
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }

    const { activeSession } = get();
    if (!activeSession) {
      return;
    }

    const userMessageId = `msg-user-${Date.now()}`;
    const userMessage = {
      id: userMessageId,
      sender: 'user' as const,
      content: trimmed,
      timestamp: Date.now(),
      referencedSnippet: get().selectedCodeSnapshot || undefined,
    };

    // 先追加用户消息，并更新状态为 generating
    set({
      activeSession: {
        ...activeSession,
        status: 'generating',
        messages: [...activeSession.messages, userMessage],
      },
    });

    // 模拟轻量模型原理解答生成
    const answer = generateLocalExplainerAnswer(trimmed, activeSession.snapshot);

    const assistantMessage = {
      id: `msg-assistant-${Date.now() + 1}`,
      sender: 'assistant' as const,
      content: answer,
      timestamp: Date.now() + 1,
    };

    set((state) => {
      if (!state.activeSession) {
        return state;
      }
      return {
        activeSession: {
          ...state.activeSession,
          status: 'idle',
          messages: [...state.activeSession.messages, assistantMessage],
        },
      };
    });
  },

  clearSession: () => {
    set({
      activeSession: null,
      selectedCodeSnapshot: null,
      isDrawerOpen: false,
    });
  },
}));
