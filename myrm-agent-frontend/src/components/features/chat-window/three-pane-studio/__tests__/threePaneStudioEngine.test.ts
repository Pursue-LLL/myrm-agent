/**
 * [INPUT]
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioEngine
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioTypes
 *
 * [OUTPUT]
 * - Unit test suite for pure computational functions in threePaneStudioEngine.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  findNodeById,
  findNodeByPath,
  findAncestorNodeIds,
  updateNodeStatusAndHighlight,
  buildDefaultContextTree,
  dispatchStudioToolEvent,
} from '../threePaneStudioEngine';
import type { ContextTreeNode } from '../threePaneStudioTypes';

describe('threePaneStudioEngine', () => {
  const sampleTree: readonly ContextTreeNode[] = [
    {
      id: 'root-user',
      label: 'User Memory',
      type: 'user_memory',
      path: 'user://memory',
      children: [
        {
          id: 'mem-1',
          label: 'Coding Style Preference',
          type: 'user_memory',
          path: 'user://memory/coding-style',
          content: 'Strict TypeScript without any.',
          status: 'idle',
        },
      ],
    },
    {
      id: 'root-res',
      label: 'Workspace Resources',
      type: 'resource',
      path: '/workspace',
      children: [
        {
          id: 'dir-src',
          label: 'src',
          type: 'resource',
          path: '/workspace/src',
          children: [
            {
              id: 'file-main',
              label: 'main.ts',
              type: 'resource',
              path: '/workspace/src/main.ts',
              content: 'console.log("hello");',
              status: 'idle',
            },
          ],
        },
      ],
    },
  ];

  describe('findNodeById', () => {
    it('should locate root node by id', () => {
      const found = findNodeById(sampleTree, 'root-user');
      expect(found).not.toBeNull();
      expect(found?.label).toBe('User Memory');
    });

    it('should locate nested leaf node by id', () => {
      const found = findNodeById(sampleTree, 'file-main');
      expect(found).not.toBeNull();
      expect(found?.label).toBe('main.ts');
      expect(found?.content).toBe('console.log("hello");');
    });

    it('should return null when node is not found', () => {
      const found = findNodeById(sampleTree, 'non-existent-id');
      expect(found).toBeNull();
    });
  });

  describe('findNodeByPath', () => {
    it('should locate node using exact path match', () => {
      const found = findNodeByPath(sampleTree, '/workspace/src/main.ts');
      expect(found).not.toBeNull();
      expect(found?.id).toBe('file-main');
    });

    it('should locate node using relative suffix or Windows backslash path', () => {
      const found = findNodeByPath(sampleTree, 'src\\main.ts');
      expect(found).not.toBeNull();
      expect(found?.id).toBe('file-main');
    });

    it('should return null for non-matching path', () => {
      const found = findNodeByPath(sampleTree, '/unknown/path.ts');
      expect(found).toBeNull();
    });
  });

  describe('findAncestorNodeIds', () => {
    it('should compute full ancestor id chain for deeply nested leaf', () => {
      const ancestors = findAncestorNodeIds(sampleTree, 'file-main');
      expect(ancestors).toEqual(['root-res', 'dir-src']);
    });

    it('should return empty array for root node', () => {
      const ancestors = findAncestorNodeIds(sampleTree, 'root-user');
      expect(ancestors).toEqual([]);
    });

    it('should return direct parent for first-level child', () => {
      const ancestors = findAncestorNodeIds(sampleTree, 'mem-1');
      expect(ancestors).toEqual(['root-user']);
    });
  });

  describe('updateNodeStatusAndHighlight', () => {
    it('should update target node status, set activeHighlight and clear existing highlights', () => {
      const treeWithPriorHighlight: readonly ContextTreeNode[] = [
        {
          id: 'node-a',
          label: 'A',
          type: 'resource',
          path: '/a',
          activeHighlight: true,
        },
        {
          id: 'node-b',
          label: 'B',
          type: 'resource',
          path: '/b',
          activeHighlight: false,
        },
      ];

      const updated = updateNodeStatusAndHighlight(
        treeWithPriorHighlight,
        'node-b',
        'reading',
        true,
      );

      const nodeA = findNodeById(updated, 'node-a');
      const nodeB = findNodeById(updated, 'node-b');

      expect(nodeA?.activeHighlight).toBe(false);
      expect(nodeB?.activeHighlight).toBe(true);
      expect(nodeB?.status).toBe('reading');
    });
  });

  describe('buildDefaultContextTree', () => {
    it('should generate standard three-root tree when input is empty', () => {
      const tree = buildDefaultContextTree();
      expect(tree).toHaveLength(3);
      expect(tree[0].id).toBe('root-user-memory');
      expect(tree[1].id).toBe('root-workspace-resources');
      expect(tree[2].id).toBe('root-agent-skills');
    });

    it('should populate memories, resources, and skills when provided', () => {
      const tree = buildDefaultContextTree({
        memories: [{ id: 'm1', title: 'User Tone', content: 'Professional' }],
        resources: [{ id: 'r1', name: 'README.md', path: '/workspace/README.md', content: '# Docs' }],
        skills: [{ id: 's1', name: 'git_curator', description: 'Curates git commits' }],
      });

      expect(tree[0].children).toHaveLength(1);
      expect(tree[0].children?.[0].label).toBe('User Tone');
      expect(tree[1].children).toHaveLength(1);
      expect(tree[1].children?.[0].label).toBe('README.md');
      expect(tree[2].children).toHaveLength(1);
      expect(tree[2].children?.[0].label).toBe('git_curator');
    });
  });

  describe('dispatchStudioToolEvent', () => {
    it('should dispatch custom browser event with tool detail', () => {
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

      const dispatched = dispatchStudioToolEvent({
        toolName: 'read_file',
        targetPath: '/workspace/src/main.ts',
        actionType: 'read',
        timestamp: 123456,
      });

      expect(dispatched).toBe(true);
      expect(dispatchSpy).toHaveBeenCalled();
      dispatchSpy.mockRestore();
    });
  });
});
