/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveTypes
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveEngine
 *
 * [OUTPUT]
 * - useSessionBranchArchiveStore (POS: Central reactive store for session branch archive and clean reset)
 *
 * [POS]
 * Central reactive dispatcher for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite.
 * Manages read-only archived snapshots, zero-anxiety /new clean restarts, rule version persistence,
 * and exploration branch tree state.
 */

import { create } from 'zustand';
import type {
  SessionBranchArchiveStoreState,
  SessionSnapshot,
} from './sessionBranchArchiveTypes';
import {
  createSessionSnapshot,
  forkBranchNode,
  findBranchNodeById,
  dispatchSessionBranchEvent,
} from './sessionBranchArchiveEngine';

export interface SessionArchiveInput {
  readonly title: string;
  readonly messageCount: number;
  readonly totalTokens: number;
  readonly summary?: string;
  readonly tags?: readonly string[];
}

export interface SessionBranchArchiveStoreActions {
  readonly setCurrentSessionId: (sessionId: string) => void;
  readonly setCurrentRuleHash: (hash: string) => void;
  readonly archiveAndResetSession: (sessionMeta: SessionArchiveInput) => {
    readonly newSessionId: string;
    readonly snapshot: SessionSnapshot;
  };
  readonly forkBranchFromMessage: (
    checkpointMessageId: string,
    branchTitle?: string,
  ) => string;
  readonly switchActiveBranch: (branchId: string) => boolean;
  readonly setArchiveModalOpen: (open: boolean) => void;
  readonly removeSnapshot: (snapshotId: string) => boolean;
  readonly resetStore: () => void;
}

export type SessionBranchArchiveStore = SessionBranchArchiveStoreState &
  SessionBranchArchiveStoreActions;

const initialState: SessionBranchArchiveStoreState = {
  currentSessionId: 'sess-initial',
  currentRuleHash: 'rule-baseline',
  snapshots: [],
  branchRoot: null,
  activeBranchId: null,
  isArchiveModalOpen: false,
  lastArchivedSnapshot: null,
};

export const useSessionBranchArchiveStore = create<SessionBranchArchiveStore>((set, get) => ({
  ...initialState,

  setCurrentSessionId: (sessionId: string) => {
    set({ currentSessionId: sessionId });
  },

  setCurrentRuleHash: (hash: string) => {
    set({ currentRuleHash: hash });
  },

  archiveAndResetSession: (sessionMeta: SessionArchiveInput) => {
    const { currentSessionId, currentRuleHash, snapshots } = get();

    const snapshot = createSessionSnapshot({
      id: `snap-${currentSessionId}-${Date.now()}`,
      title: sessionMeta.title,
      summary: sessionMeta.summary,
      messageCount: sessionMeta.messageCount,
      totalTokens: sessionMeta.totalTokens,
      ruleHash: currentRuleHash,
      tags: sessionMeta.tags,
      archivedAt: Date.now(),
    });

    const newSessionId = `sess-${Date.now()}`;

    dispatchSessionBranchEvent({
      action: 'archive_and_reset',
      sessionId: newSessionId,
      snapshotId: snapshot.id,
      timestamp: Date.now(),
    });

    set({
      currentSessionId: newSessionId,
      snapshots: [snapshot, ...snapshots],
      lastArchivedSnapshot: snapshot,
    });

    return {
      newSessionId,
      snapshot,
    };
  },

  forkBranchFromMessage: (checkpointMessageId: string, branchTitle = '探索分支') => {
    const { branchRoot, currentSessionId } = get();
    const newBranchId = `branch-${Date.now()}`;

    const newRoot = forkBranchNode(branchRoot, branchRoot ? branchRoot.id : null, {
      id: newBranchId,
      title: branchTitle,
      checkpointMessageId,
      createdAt: Date.now(),
    });

    dispatchSessionBranchEvent({
      action: 'fork_branch',
      sessionId: currentSessionId,
      branchId: newBranchId,
      timestamp: Date.now(),
    });

    set({
      branchRoot: newRoot,
      activeBranchId: newBranchId,
    });

    return newBranchId;
  },

  switchActiveBranch: (branchId: string) => {
    const { branchRoot, currentSessionId } = get();
    const target = findBranchNodeById(branchRoot, branchId);
    if (!target) {
      return false;
    }

    dispatchSessionBranchEvent({
      action: 'switch_branch',
      sessionId: currentSessionId,
      branchId,
      timestamp: Date.now(),
    });

    set({ activeBranchId: branchId });
    return true;
  },

  setArchiveModalOpen: (open: boolean) => {
    set({ isArchiveModalOpen: open });
  },

  removeSnapshot: (snapshotId: string) => {
    const { snapshots } = get();
    const filtered = snapshots.filter((s) => s.id !== snapshotId);
    if (filtered.length === snapshots.length) {
      return false;
    }

    set({ snapshots: filtered });
    return true;
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
