/**
 * [INPUT]
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveTypes
 *
 * [OUTPUT]
 * - createSessionSnapshot, forkBranchNode, findBranchNodeById,
 *   flattenBranchTree, calculateContextHygiene, dispatchSessionBranchEvent
 *
 * [POS]
 * Pure computation engine for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite.
 * Operates on immutable branch trees, constructs read-only session snapshots,
 * computes context hygiene metrics, and broadcasts session lifecycle events.
 */

import type {
  SessionSnapshot,
  SessionBranchNode,
  ContextHygieneMetrics,
  SessionBranchEventPayload,
} from './sessionBranchArchiveTypes';

export function createSessionSnapshot(input: {
  readonly id: string;
  readonly title: string;
  readonly summary?: string;
  readonly messageCount: number;
  readonly totalTokens: number;
  readonly ruleHash: string;
  readonly tags?: readonly string[];
  readonly archivedAt?: number;
}): SessionSnapshot {
  return {
    id: input.id,
    title: input.title,
    summary: input.summary,
    messageCount: input.messageCount,
    totalTokens: input.totalTokens,
    archivedAt: input.archivedAt ?? Date.now(),
    ruleHash: input.ruleHash,
    tags: input.tags ?? ['auto-archive'],
  };
}

export function forkBranchNode(
  root: SessionBranchNode | null,
  parentId: string | null,
  newBranchInput: {
    readonly id: string;
    readonly title: string;
    readonly checkpointMessageId: string;
    readonly createdAt?: number;
  },
): SessionBranchNode {
  const newNode: SessionBranchNode = {
    id: newBranchInput.id,
    parentId,
    title: newBranchInput.title,
    checkpointMessageId: newBranchInput.checkpointMessageId,
    createdAt: newBranchInput.createdAt ?? Date.now(),
    children: [],
  };

  if (!root || !parentId) {
    return newNode;
  }

  function insertRecursive(current: SessionBranchNode): SessionBranchNode {
    if (current.id === parentId) {
      return {
        ...current,
        children: [...current.children, newNode],
      };
    }

    if (current.children.length === 0) {
      return current;
    }

    return {
      ...current,
      children: current.children.map(insertRecursive),
    };
  }

  return insertRecursive(root);
}

export function findBranchNodeById(
  root: SessionBranchNode | null,
  targetId: string,
): SessionBranchNode | null {
  if (!root) {
    return null;
  }

  if (root.id === targetId) {
    return root;
  }

  for (const child of root.children) {
    const found = findBranchNodeById(child, targetId);
    if (found) {
      return found;
    }
  }

  return null;
}

export function flattenBranchTree(
  root: SessionBranchNode | null,
): readonly SessionBranchNode[] {
  if (!root) {
    return [];
  }

  const result: SessionBranchNode[] = [root];
  for (const child of root.children) {
    result.push(...flattenBranchTree(child));
  }
  return result;
}

export function calculateContextHygiene(
  beforeTokens: number,
  baselineRuleTokens = 1200,
): ContextHygieneMetrics {
  const afterTokens = Math.max(0, baselineRuleTokens);
  const tokensSaved = Math.max(0, beforeTokens - afterTokens);
  return {
    beforeTokens,
    afterTokens,
    tokensSaved,
    ruleCoveragePercent: 100,
  };
}

export function dispatchSessionBranchEvent(payload: SessionBranchEventPayload): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    const event = new CustomEvent('myrm:session-branch-archived', {
      detail: payload,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(event);
    return true;
  } catch {
    return false;
  }
}
