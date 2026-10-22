/**
 * [INPUT]
 * - None (Pure domain type definitions for Session Branch Archive & Rule Preserved Reset)
 *
 * [OUTPUT]
 * - SessionSnapshot, SessionBranchNode, ContextHygieneMetrics,
 *   SessionBranchEventPayload, SessionBranchArchiveStoreState
 *
 * [POS]
 * Unified contracts for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite.
 * Embodies the "Rules in Files, Process in Session" philosophy, enabling zero-anxiety
 * /new clean restarts, read-only session snapshot archiving, and exploration tree branching.
 */

export interface SessionSnapshot {
  readonly id: string;
  readonly title: string;
  readonly summary?: string;
  readonly messageCount: number;
  readonly totalTokens: number;
  readonly archivedAt: number;
  readonly ruleHash: string;
  readonly tags?: readonly string[];
}

export interface SessionBranchNode {
  readonly id: string;
  readonly parentId: string | null;
  readonly title: string;
  readonly checkpointMessageId: string;
  readonly createdAt: number;
  readonly children: readonly SessionBranchNode[];
}

export interface ContextHygieneMetrics {
  readonly beforeTokens: number;
  readonly afterTokens: number;
  readonly tokensSaved: number;
  readonly ruleCoveragePercent: number;
}

export interface SessionBranchEventPayload {
  readonly action: 'archive_and_reset' | 'fork_branch' | 'switch_branch';
  readonly sessionId: string;
  readonly branchId?: string;
  readonly snapshotId?: string;
  readonly timestamp: number;
}

export interface SessionBranchArchiveStoreState {
  readonly currentSessionId: string;
  readonly currentRuleHash: string;
  readonly snapshots: readonly SessionSnapshot[];
  readonly branchRoot: SessionBranchNode | null;
  readonly activeBranchId: string | null;
  readonly isArchiveModalOpen: boolean;
  readonly lastArchivedSnapshot: SessionSnapshot | null;
}
