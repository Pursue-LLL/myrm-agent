import { create } from 'zustand';
import {
  ApprovalAction,
  LoopPhase,
  LoopTaskStep,
  PetMood,
  PetSpeechLoopState,
  VoiceCaptureStatus,
} from './petSpeechLoopTypes';
import {
  advanceStepStage,
  buildApprovalActionPayload,
  decomposeSpeechPrompt,
  deriveBubbleMessage,
  derivePetMoodByPhase,
} from './petSpeechLoopEngine';

export interface PetSpeechLoopActions {
  startVoiceCapture: () => void;
  stopVoiceCapture: () => void;
  feedVoiceInput: (text: string, isFinal?: boolean) => void;
  triggerSpeechPromptLoop: (prompt: string) => void;
  advanceToNextPhase: () => void;
  runFullCycle: (prompt: string) => void;
  toggleApprovalDrawer: (open?: boolean) => void;
  approveAction: () => void;
  rejectAction: () => void;
  setBubbleMessage: (msg: string | null) => void;
  reset: () => void;
}

export type PetSpeechLoopStore = PetSpeechLoopState & PetSpeechLoopActions;

const initialState: PetSpeechLoopState = {
  currentPhase: 'idle',
  voiceStatus: 'inactive',
  transcript: '',
  interimTranscript: '',
  steps: [],
  approvalAction: null,
  isApprovalDrawerOpen: false,
  petMood: 'calm',
  bubbleMessage: null,
  isWiggling: false,
};

export const usePetSpeechLoopStore = create<PetSpeechLoopStore>((set, get) => ({
  ...initialState,

  startVoiceCapture: () => {
    set({
      voiceStatus: 'listening',
      currentPhase: 'listening',
      petMood: 'listening',
      bubbleMessage: '我在听，请随时说出你的想法…',
      interimTranscript: '',
    });
  },

  stopVoiceCapture: () => {
    set({
      voiceStatus: 'inactive',
      interimTranscript: '',
    });
  },

  feedVoiceInput: (text: string, isFinal = false) => {
    if (!isFinal) {
      set({
        interimTranscript: text,
        bubbleMessage: text.trim() ? `听取中: "${text}"` : '我在听…',
      });
      return;
    }

    set({
      transcript: text,
      interimTranscript: '',
      voiceStatus: 'inactive',
    });

    get().triggerSpeechPromptLoop(text);
  },

  triggerSpeechPromptLoop: (prompt: string) => {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt) {
      return;
    }

    const steps = decomposeSpeechPrompt(cleanPrompt);
    const approval = buildApprovalActionPayload(cleanPrompt, steps);

    // 第一阶段：planning
    set({
      transcript: cleanPrompt,
      currentPhase: 'planning',
      petMood: derivePetMoodByPhase('planning'),
      bubbleMessage: deriveBubbleMessage('planning', cleanPrompt),
      steps: advanceStepStage(steps, 'plan', 'running'),
      approvalAction: approval,
      isApprovalDrawerOpen: false,
      isWiggling: false,
    });
  },

  advanceToNextPhase: () => {
    const { currentPhase, steps, transcript, approvalAction } = get();

    switch (currentPhase) {
      case 'planning': {
        const updated = advanceStepStage(steps, 'plan', 'completed', 450);
        set({
          currentPhase: 'coding',
          petMood: derivePetMoodByPhase('coding'),
          bubbleMessage: deriveBubbleMessage('coding'),
          steps: advanceStepStage(updated, 'code', 'running'),
        });
        break;
      }
      case 'coding': {
        const updated = advanceStepStage(steps, 'code', 'completed', 820);
        set({
          currentPhase: 'executing',
          petMood: derivePetMoodByPhase('executing'),
          bubbleMessage: deriveBubbleMessage('executing'),
          steps: advanceStepStage(updated, 'exec', 'running'),
        });
        break;
      }
      case 'executing': {
        const updated = advanceStepStage(steps, 'exec', 'completed', 610);
        const verified = advanceStepStage(updated, 'verify', 'completed', 320);
        set({
          currentPhase: 'reviewing',
          petMood: derivePetMoodByPhase('reviewing'),
          bubbleMessage: deriveBubbleMessage('reviewing'),
          steps: verified,
          isApprovalDrawerOpen: true,
        });
        break;
      }
      case 'reviewing': {
        set({
          currentPhase: 'completed',
          petMood: derivePetMoodByPhase('completed'),
          bubbleMessage: deriveBubbleMessage('completed', transcript),
          isApprovalDrawerOpen: false,
          isWiggling: true,
        });
        break;
      }
      case 'completed': {
        set({
          currentPhase: 'idle',
          petMood: 'calm',
          bubbleMessage: null,
          isWiggling: false,
        });
        break;
      }
      default: {
        break;
      }
    }
  },

  runFullCycle: (prompt: string) => {
    get().triggerSpeechPromptLoop(prompt);
    // 顺序模拟执行各阶段
    get().advanceToNextPhase(); // planning -> coding
    get().advanceToNextPhase(); // coding -> executing
    get().advanceToNextPhase(); // executing -> reviewing
  },

  toggleApprovalDrawer: (open) => {
    set((state) => ({
      isApprovalDrawerOpen:
        typeof open === 'boolean' ? open : !state.isApprovalDrawerOpen,
    }));
  },

  approveAction: () => {
    const { approvalAction } = get();
    if (approvalAction) {
      set({
        approvalAction: {
          ...approvalAction,
          status: 'approved',
        },
      });
    }

    set({
      isApprovalDrawerOpen: false,
      currentPhase: 'completed',
      petMood: 'celebrating',
      bubbleMessage: '修改已批准落地！正在庆祝成果！',
      isWiggling: true,
    });
  },

  rejectAction: () => {
    const { approvalAction } = get();
    if (approvalAction) {
      set({
        approvalAction: {
          ...approvalAction,
          status: 'rejected',
        },
      });
    }

    set({
      isApprovalDrawerOpen: false,
      currentPhase: 'idle',
      petMood: 'calm',
      bubbleMessage: '已取消本次变更计划，随时待命。',
      isWiggling: false,
    });
  },

  setBubbleMessage: (msg: string | null) => {
    set({ bubbleMessage: msg });
  },

  reset: () => {
    set(initialState);
  },
}));
