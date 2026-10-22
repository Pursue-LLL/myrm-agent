/**
 * [INPUT]
 * - @/components/features/chat-window/session-branch-archive/useSessionBranchArchiveStore
 *
 * [OUTPUT]
 * - Unit test suite for useSessionBranchArchiveStore state transitions, snapshot creation, and branching.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useSessionBranchArchiveStore } from '../useSessionBranchArchiveStore';

describe('useSessionBranchArchiveStore', () => {
  beforeEach(() => {
    useSessionBranchArchiveStore.getState().resetStore();
  });

  it('should initialize with default state', () => {
    const state = useSessionBranchArchiveStore.getState();
    expect(state.currentSessionId).toBe('sess-initial');
    expect(state.currentRuleHash).toBe('rule-baseline');
    expect(state.snapshots).toHaveLength(0);
    expect(state.branchRoot).toBeNull();
    expect(state.activeBranchId).toBeNull();
    expect(state.isArchiveModalOpen).toBe(false);
    expect(state.lastArchivedSnapshot).toBeNull();
  });

  it('should update current sessionId and rule hash', () => {
    const store = useSessionBranchArchiveStore.getState();
    store.setCurrentSessionId('sess-custom-1');
    store.setCurrentRuleHash('rule-hash-v2');

    expect(useSessionBranchArchiveStore.getState().currentSessionId).toBe('sess-custom-1');
    expect(useSessionBranchArchiveStore.getState().currentRuleHash).toBe('rule-hash-v2');
  });

  it('should archive current session and perform clean reset with new session ID', () => {
    const store = useSessionBranchArchiveStore.getState();
    store.setCurrentSessionId('sess-long-running');
    store.setCurrentRuleHash('rule-hash-v1');

    const result = store.archiveAndResetSession({
      title: 'Milestone 1 Archive',
      messageCount: 50,
      totalTokens: 45000,
      summary: 'Authentication complete',
      tags: ['sprint-1'],
    });

    expect(result.snapshot.title).toBe('Milestone 1 Archive');
    expect(result.snapshot.ruleHash).toBe('rule-hash-v1');
    expect(result.newSessionId).not.toBe('sess-long-running');

    const updated = useSessionBranchArchiveStore.getState();
    expect(updated.currentSessionId).toBe(result.newSessionId);
    expect(updated.snapshots).toHaveLength(1);
    expect(updated.snapshots[0].id).toBe(result.snapshot.id);
    expect(updated.lastArchivedSnapshot?.id).toBe(result.snapshot.id);
  });

  it('should fork branch from message checkpoint and switch active branch', () => {
    const store = useSessionBranchArchiveStore.getState();
    const branchId1 = store.forkBranchFromMessage('msg-checkpoint-1', '探索算法A');

    expect(branchId1).toBeTruthy();
    const state1 = useSessionBranchArchiveStore.getState();
    expect(state1.branchRoot?.id).toBe(branchId1);
    expect(state1.activeBranchId).toBe(branchId1);

    const branchId2 = store.forkBranchFromMessage('msg-checkpoint-2', '探索算法B');
    const state2 = useSessionBranchArchiveStore.getState();
    expect(state2.activeBranchId).toBe(branchId2);
    expect(state2.branchRoot?.children).toHaveLength(1);

    const switched = store.switchActiveBranch(branchId1);
    expect(switched).toBe(true);
    expect(useSessionBranchArchiveStore.getState().activeBranchId).toBe(branchId1);

    const switchNonExistent = store.switchActiveBranch('non-existent-branch');
    expect(switchNonExistent).toBe(false);
  });

  it('should toggle archive modal visibility and remove snapshots', () => {
    const store = useSessionBranchArchiveStore.getState();
    store.setArchiveModalOpen(true);
    expect(useSessionBranchArchiveStore.getState().isArchiveModalOpen).toBe(true);

    const { snapshot } = store.archiveAndResetSession({
      title: 'To Be Removed',
      messageCount: 10,
      totalTokens: 5000,
    });
    expect(useSessionBranchArchiveStore.getState().snapshots).toHaveLength(1);

    const removedNonExistent = store.removeSnapshot('unknown-snap');
    expect(removedNonExistent).toBe(false);

    const removed = store.removeSnapshot(snapshot.id);
    expect(removed).toBe(true);
    expect(useSessionBranchArchiveStore.getState().snapshots).toHaveLength(0);
  });
});
