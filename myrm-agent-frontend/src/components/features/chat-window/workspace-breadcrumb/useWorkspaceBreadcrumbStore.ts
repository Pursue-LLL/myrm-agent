/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbTypes
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbEngine
 *
 * [OUTPUT]
 * - useWorkspaceBreadcrumbStore (POS: Central reactive store for workspace breadcrumb path and desktop reveal)
 *
 * [POS]
 * Central reactive dispatcher for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite.
 * Manages active session workspace physical paths, copy status feedback,
 * and desktop Finder/Terminal bridge invocation.
 */

import { create } from 'zustand';
import type {
  WorkspaceBreadcrumbStoreState,
  WorkspaceLocationInfo,
  WorkspaceRevealAction,
} from './workspaceBreadcrumbTypes';
import {
  parseWorkspacePath,
  dispatchWorkspaceRevealEvent,
} from './workspaceBreadcrumbEngine';

export interface WorkspaceBreadcrumbStoreActions {
  readonly setActiveChatId: (chatId: string | null) => void;
  readonly setWorkspacePath: (chatId: string, path: string) => void;
  readonly setDefaultPath: (path: string) => void;
  readonly getCurrentPath: () => string;
  readonly getLocationInfo: (pathOverride?: string) => WorkspaceLocationInfo;
  readonly revealInFinder: (pathOverride?: string) => boolean;
  readonly revealInTerminal: (pathOverride?: string) => boolean;
  readonly copyCurrentPath: (pathOverride?: string) => Promise<boolean>;
  readonly resetCopied: () => void;
  readonly resetStore: () => void;
}

export type WorkspaceBreadcrumbStore = WorkspaceBreadcrumbStoreState &
  WorkspaceBreadcrumbStoreActions;

const initialState: WorkspaceBreadcrumbStoreState = {
  workspacePathByChatId: {},
  activeChatId: null,
  defaultPath: '/workspace',
  lastRevealedAction: null,
  isCopied: false,
};

export const useWorkspaceBreadcrumbStore = create<WorkspaceBreadcrumbStore>((set, get) => ({
  ...initialState,

  setActiveChatId: (chatId: string | null) => {
    set({ activeChatId: chatId, isCopied: false });
  },

  setWorkspacePath: (chatId: string, path: string) => {
    set((state) => ({
      workspacePathByChatId: {
        ...state.workspacePathByChatId,
        [chatId]: path,
      },
    }));
  },

  setDefaultPath: (path: string) => {
    set({ defaultPath: path });
  },

  getCurrentPath: () => {
    const { activeChatId, workspacePathByChatId, defaultPath } = get();
    if (activeChatId && workspacePathByChatId[activeChatId]) {
      return workspacePathByChatId[activeChatId];
    }
    return defaultPath;
  },

  getLocationInfo: (pathOverride?: string) => {
    const currentPath = pathOverride || get().getCurrentPath();
    return parseWorkspacePath(currentPath);
  },

  revealInFinder: (pathOverride?: string) => {
    const currentPath = pathOverride || get().getCurrentPath();
    const dispatched = dispatchWorkspaceRevealEvent({
      action: 'finder',
      path: currentPath,
      timestamp: Date.now(),
    });
    set({ lastRevealedAction: 'finder' });
    return dispatched;
  },

  revealInTerminal: (pathOverride?: string) => {
    const currentPath = pathOverride || get().getCurrentPath();
    const dispatched = dispatchWorkspaceRevealEvent({
      action: 'terminal',
      path: currentPath,
      timestamp: Date.now(),
    });
    set({ lastRevealedAction: 'terminal' });
    return dispatched;
  },

  copyCurrentPath: async (pathOverride?: string) => {
    const currentPath = pathOverride || get().getCurrentPath();
    let copiedSuccess = false;

    if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      try {
        await navigator.clipboard.writeText(currentPath);
        copiedSuccess = true;
      } catch {
        copiedSuccess = false;
      }
    }

    dispatchWorkspaceRevealEvent({
      action: 'copy_path',
      path: currentPath,
      timestamp: Date.now(),
    });

    set({ isCopied: true, lastRevealedAction: 'copy_path' });
    return copiedSuccess;
  },

  resetCopied: () => {
    set({ isCopied: false });
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
