/**
 * [INPUT]
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveTypes
 *
 * [OUTPUT]
 * - Domain contracts and type assertion tests for Item 200.
 */

import { describe, it, expect } from 'vitest';
import type {
  SessionSnapshot,
  SessionBranchNode,
  ContextHygieneMetrics,
  SessionBranchEventPayload,
  SessionBranchArchiveStoreState,
} from '../sessionBranchArchiveTypes';

describe('SessionBranchArchiveTypes Contracts', () => {
  it('should construct a valid SessionSnapshot entity', () => {
    const snapshot: SessionSnapshot = {
      id: 'snap-1',
      title: 'Milestone 1 Archive',
      summary: 'Authentication and storage implemented',
      messageCount: 42,
      totalTokens: 38400,
      archivedAt: 1760000000000,
      ruleHash: 'a1b2c3d4',
      tags: ['auth', 'phase-1'],
    };

    expect(snapshot.id).toBe('snap-1');
    expect(snapshot.messageCount).toBe(42);
    expect(snapshot.ruleHash).toBe('a1b2c3d4');
    expect(snapshot.tags).toContain('phase-1');
  });

  it('should construct a hierarchical SessionBranchNode tree', () => {
    const childBranch: SessionBranchNode = {
      id: 'branch-child',
      parentId: 'branch-root',
      title: 'Alternative Solution',
      checkpointMessageId: 'msg-10',
      createdAt: 1760000001000,
      children: [],
    };

    const rootBranch: SessionBranchNode = {
      id: 'branch-root',
      parentId: null,
      title: 'Main Branch',
      checkpointMessageId: 'msg-1',
      createdAt: 1760000000000,
      children: [childBranch],
    };

    expect(rootBranch.parentId).toBeNull();
    expect(rootBranch.children).toHaveLength(1);
    expect(rootBranch.children[0].parentId).toBe('branch-root');
  });

  it('should conform to ContextHygieneMetrics and EventPayload contracts', () => {
    const metrics: ContextHygieneMetrics = {
      beforeTokens: 45000,
      afterTokens: 1200,
      tokensSaved: 43800,
      ruleCoveragePercent: 100,
    };

    const payload: SessionBranchEventPayload = {
      action: 'archive_and_reset',
      sessionId: 'sess-new-1',
      snapshotId: 'snap-1',
      timestamp: 1760000002000,
    };

    expect(metrics.tokensSaved).toBe(43800);
    expect(metrics.ruleCoveragePercent).toBe(100);
    expect(payload.action).toBe('archive_and_reset');
    expect(payload.sessionId).toBe('sess-new-1');
  });

  it('should construct a valid SessionBranchArchiveStoreState entity', () => {
    const state: SessionBranchArchiveStoreState = {
      currentSessionId: 'sess-100',
      currentRuleHash: 'rule-hash-v1',
      snapshots: [],
      branchRoot: null,
      activeBranchId: null,
      isArchiveModalOpen: false,
      lastArchivedSnapshot: null,
    };

    expect(state.currentSessionId).toBe('sess-100');
    expect(state.isArchiveModalOpen).toBe(false);
  });
});
