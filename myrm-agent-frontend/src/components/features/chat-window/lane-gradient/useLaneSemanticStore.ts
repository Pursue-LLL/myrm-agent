/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/store/useChatStore (POS: Downstream connection to actionMode, sandboxMode, workspaceDir)
 * - @/components/features/chat-window/lane-gradient/laneSemanticTypes
 * - @/components/features/chat-window/lane-gradient/laneSemanticEngine
 *
 * [OUTPUT]
 * - useLaneSemanticStore (POS: Reactive store for lane gradient and in-session graduation)
 *
 * [POS]
 * Bridges user boundary crossings to concrete chat store actions. Seamlessly upgrades
 * an in-flight conversation from Chat Lane to Workspace Lane without dropping messages or resetting history.
 */

import { create } from 'zustand';
import useChatStore from '@/store/useChatStore';
import type {
  LaneType,
  LaneSemanticStoreState,
  GraduationIntentMatch,
  LaneGraduationEvent,
} from './laneSemanticTypes';
import {
  resolveLaneGradientSpec,
  detectGraduationIntent,
  buildGraduationEvent,
} from './laneSemanticEngine';

export interface LaneSemanticStoreActions {
  readonly evaluateInputIntent: (text: string) => GraduationIntentMatch | null;
  readonly setPendingGraduation: (match: GraduationIntentMatch | null) => void;
  readonly openGraduationDialog: () => void;
  readonly closeGraduationDialog: () => void;
  readonly graduateToWorkspace: (
    targetMode: 'local_workspace' | 'cloud_sandbox',
    customWorkspaceDir?: string | null,
  ) => void;
  readonly dismissGraduation: () => void;
  readonly setManualLaneOverride: (lane: LaneType | null) => void;
  readonly clearHistory: () => void;
}

export type LaneSemanticStore = LaneSemanticStoreState & LaneSemanticStoreActions;

export const useLaneSemanticStore = create<LaneSemanticStore>((set, get) => ({
  manualLaneOverride: null,
  pendingGraduation: null,
  isGraduationDialogOpen: false,
  graduationHistory: [],

  evaluateInputIntent: (text: string): GraduationIntentMatch | null => {
    const chatState = useChatStore.getState();
    const currentSpec = resolveLaneGradientSpec(
      chatState.actionMode,
      chatState.sandboxMode,
      chatState.workspaceDir,
    );

    const activeLane = get().manualLaneOverride ?? currentSpec.laneType;
    const match = detectGraduationIntent(text, activeLane);

    if (match) {
      set({
        pendingGraduation: match,
        isGraduationDialogOpen: true,
      });
      return match;
    }

    return null;
  },

  setPendingGraduation: (match: GraduationIntentMatch | null) => {
    set({
      pendingGraduation: match,
      isGraduationDialogOpen: Boolean(match),
    });
  },

  openGraduationDialog: () => {
    set({ isGraduationDialogOpen: true });
  },

  closeGraduationDialog: () => {
    set({ isGraduationDialogOpen: false });
  },

  graduateToWorkspace: (
    targetMode: 'local_workspace' | 'cloud_sandbox',
    customWorkspaceDir?: string | null,
  ) => {
    const chatStore = useChatStore.getState();
    const currentSpec = resolveLaneGradientSpec(
      chatStore.actionMode,
      chatStore.sandboxMode,
      chatStore.workspaceDir,
    );

    const reason = get().pendingGraduation?.reason ?? '用户主动升级到工作区通道';
    const chosenDir =
      targetMode === 'local_workspace'
        ? (customWorkspaceDir ?? chatStore.workspaceDir ?? '/workspace')
        : null;

    const graduationEvent: LaneGraduationEvent = buildGraduationEvent({
      fromSpec: currentSpec,
      toEnvMode: targetMode,
      reason,
      workspaceDir: chosenDir,
    });

    // Synchronize to global chat store
    if (targetMode === 'cloud_sandbox') {
      chatStore.setSandboxMode(true);
      chatStore.setActionMode('agent');
    } else {
      chatStore.setSandboxMode(false);
      chatStore.setActionMode('agent');
      if (chosenDir) {
        chatStore.setWorkspaceDir(chosenDir);
      }
    }

    set((state) => ({
      pendingGraduation: null,
      isGraduationDialogOpen: false,
      manualLaneOverride: null,
      graduationHistory: [graduationEvent, ...state.graduationHistory],
    }));
  },

  dismissGraduation: () => {
    set({
      pendingGraduation: null,
      isGraduationDialogOpen: false,
    });
  },

  setManualLaneOverride: (lane: LaneType | null) => {
    set({ manualLaneOverride: lane });
  },

  clearHistory: () => {
    set({ graduationHistory: [] });
  },
}));
