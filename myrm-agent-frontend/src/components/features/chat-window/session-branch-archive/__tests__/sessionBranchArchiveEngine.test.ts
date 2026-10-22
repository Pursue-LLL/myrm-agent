/**
 * [INPUT]
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveEngine
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveTypes
 *
 * [OUTPUT]
 * - Unit test suite for pure computational functions in sessionBranchArchiveEngine.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  createSessionSnapshot,
  forkBranchNode,
  findBranchNodeById,
  flattenBranchTree,
  calculateContextHygiene,
  dispatchSessionBranchEvent,
} from '../sessionBranchArchiveEngine';
import type { SessionBranchNode } from '../sessionBranchArchiveTypes';

describe('sessionBranchArchiveEngine', () => {
  describe('createSessionSnapshot', () => {
    it('should construct snapshot with provided properties and default tags', () => {
      const snapshot = createSessionSnapshot({
        id: 'snap-1',
        title: 'Sprint Demo',
        summary: 'Demo of three-pane studio',
        messageCount: 20,
        totalTokens: 15000,
        ruleHash: 'abcdef01',
        archivedAt: 1000,
      });

      expect(snapshot.id).toBe('snap-1');
      expect(snapshot.title).toBe('Sprint Demo');
      expect(snapshot.archivedAt).toBe(1000);
      expect(snapshot.tags).toEqual(['auto-archive']);
    });
  });

  describe('forkBranchNode', () => {
    it('should create root branch when root is null', () => {
      const root = forkBranchNode(null, null, {
        id: 'branch-1',
        title: 'Initial Branch',
        checkpointMessageId: 'msg-1',
        createdAt: 1000,
      });

      expect(root.id).toBe('branch-1');
      expect(root.parentId).toBeNull();
      expect(root.children).toHaveLength(0);
    });

    it('should append child branch under matching parentId', () => {
      const root: SessionBranchNode = {
        id: 'branch-root',
        parentId: null,
        title: 'Main',
        checkpointMessageId: 'msg-root',
        createdAt: 1000,
        children: [],
      };

      const updated = forkBranchNode(root, 'branch-root', {
        id: 'branch-child',
        title: 'Exploration 1',
        checkpointMessageId: 'msg-checkpoint-1',
        createdAt: 2000,
      });

      expect(updated.children).toHaveLength(1);
      expect(updated.children[0].id).toBe('branch-child');
      expect(updated.children[0].parentId).toBe('branch-root');
    });

    it('should recursively append child branch in deep tree', () => {
      const deepTree: SessionBranchNode = {
        id: 'root',
        parentId: null,
        title: 'Root',
        checkpointMessageId: 'msg-0',
        createdAt: 1000,
        children: [
          {
            id: 'child-1',
            parentId: 'root',
            title: 'Child 1',
            checkpointMessageId: 'msg-1',
            createdAt: 1100,
            children: [],
          },
        ],
      };

      const updated = forkBranchNode(deepTree, 'child-1', {
        id: 'grandchild-1',
        title: 'Grandchild 1',
        checkpointMessageId: 'msg-2',
        createdAt: 1200,
      });

      expect(updated.children[0].children).toHaveLength(1);
      expect(updated.children[0].children[0].id).toBe('grandchild-1');
    });
  });

  describe('findBranchNodeById', () => {
    const tree: SessionBranchNode = {
      id: 'root',
      parentId: null,
      title: 'Root',
      checkpointMessageId: 'msg-0',
      createdAt: 1000,
      children: [
        {
          id: 'child',
          parentId: 'root',
          title: 'Child',
          checkpointMessageId: 'msg-1',
          createdAt: 1100,
          children: [],
        },
      ],
    };

    it('should locate root and nested children', () => {
      expect(findBranchNodeById(tree, 'root')?.title).toBe('Root');
      expect(findBranchNodeById(tree, 'child')?.title).toBe('Child');
    });

    it('should return null for non-existent node ID or null root', () => {
      expect(findBranchNodeById(tree, 'unknown')).toBeNull();
      expect(findBranchNodeById(null, 'root')).toBeNull();
    });
  });

  describe('flattenBranchTree', () => {
    it('should return empty array for null root', () => {
      expect(flattenBranchTree(null)).toEqual([]);
    });

    it('should flatten tree into array preserving all branch nodes', () => {
      const tree: SessionBranchNode = {
        id: 'b-1',
        parentId: null,
        title: 'Branch 1',
        checkpointMessageId: 'msg-1',
        createdAt: 1000,
        children: [
          {
            id: 'b-2',
            parentId: 'b-1',
            title: 'Branch 2',
            checkpointMessageId: 'msg-2',
            createdAt: 1100,
            children: [],
          },
        ],
      };

      const flat = flattenBranchTree(tree);
      expect(flat).toHaveLength(2);
      expect(flat.map((b) => b.id)).toEqual(['b-1', 'b-2']);
    });
  });

  describe('calculateContextHygiene', () => {
    it('should compute token savings and preserve 100% rule coverage', () => {
      const hygiene = calculateContextHygiene(48000, 1500);
      expect(hygiene.beforeTokens).toBe(48000);
      expect(hygiene.afterTokens).toBe(1500);
      expect(hygiene.tokensSaved).toBe(46500);
      expect(hygiene.ruleCoveragePercent).toBe(100);
    });
  });

  describe('dispatchSessionBranchEvent', () => {
    it('should dispatch custom browser event with event detail', () => {
      const spy = vi.spyOn(window, 'dispatchEvent');

      const dispatched = dispatchSessionBranchEvent({
        action: 'archive_and_reset',
        sessionId: 'sess-test',
        timestamp: 123456,
      });

      expect(dispatched).toBe(true);
      expect(spy).toHaveBeenCalled();
      spy.mockRestore();
    });
  });
});
