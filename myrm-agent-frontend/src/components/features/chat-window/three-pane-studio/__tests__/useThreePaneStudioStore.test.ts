/**
 * [INPUT]
 * - @/components/features/chat-window/three-pane-studio/useThreePaneStudioStore
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioEngine
 *
 * [OUTPUT]
 * - Unit test suite for useThreePaneStudioStore state mutations and tool highlight workflows.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useThreePaneStudioStore } from '../useThreePaneStudioStore';
import { buildDefaultContextTree } from '../threePaneStudioEngine';

describe('useThreePaneStudioStore', () => {
  beforeEach(() => {
    useThreePaneStudioStore.getState().resetStore();
  });

  it('should initialize with standard default state', () => {
    const state = useThreePaneStudioStore.getState();
    expect(state.rootNodes).toHaveLength(3);
    expect(state.selectedNodeId).toBeNull();
    expect(state.expandedNodeIds).toContain('root-workspace-resources');
    expect(state.rightPaneMode).toBe('agent_chat');
    expect(state.layout.isLeftCollapsed).toBe(false);
    expect(state.layout.isRightCollapsed).toBe(false);
  });

  it('should handle selectNode and getSelectedNode', () => {
    const customTree = buildDefaultContextTree({
      resources: [{ id: 'doc-1', name: 'guide.md', path: '/workspace/guide.md', content: 'Guide' }],
    });

    const store = useThreePaneStudioStore.getState();
    store.setRootNodes(customTree);
    store.selectNode('res-doc-1');

    expect(useThreePaneStudioStore.getState().selectedNodeId).toBe('res-doc-1');
    const selected = useThreePaneStudioStore.getState().getSelectedNode();
    expect(selected?.label).toBe('guide.md');
    expect(selected?.content).toBe('Guide');
  });

  it('should toggle node expansion state', () => {
    const store = useThreePaneStudioStore.getState();
    store.toggleNodeExpanded('custom-dir', true);
    expect(useThreePaneStudioStore.getState().expandedNodeIds).toContain('custom-dir');

    store.toggleNodeExpanded('custom-dir', false);
    expect(useThreePaneStudioStore.getState().expandedNodeIds).not.toContain('custom-dir');

    store.toggleNodeExpanded('custom-dir');
    expect(useThreePaneStudioStore.getState().expandedNodeIds).toContain('custom-dir');
  });

  it('should switch right pane mode and layout collapse states', () => {
    const store = useThreePaneStudioStore.getState();
    store.setRightPaneMode('terminal');
    expect(useThreePaneStudioStore.getState().rightPaneMode).toBe('terminal');

    store.toggleLeftCollapse();
    expect(useThreePaneStudioStore.getState().layout.isLeftCollapsed).toBe(true);

    store.toggleRightCollapse();
    expect(useThreePaneStudioStore.getState().layout.isRightCollapsed).toBe(true);

    store.setPaneLayout({ leftWidth: 320 });
    expect(useThreePaneStudioStore.getState().layout.leftWidth).toBe(320);
  });

  it('should automatically unfold ancestors and highlight node on triggerToolHighlight', () => {
    const customTree = buildDefaultContextTree({
      resources: [
        {
          id: 'server-config',
          name: 'server.json',
          path: '/workspace/config/server.json',
          content: '{"port": 8080}',
        },
      ],
    });

    const store = useThreePaneStudioStore.getState();
    store.setRootNodes(customTree);

    const matched = store.triggerToolHighlight({
      toolName: 'read_file',
      targetPath: '/workspace/config/server.json',
      actionType: 'read',
      timestamp: 1000,
    });

    expect(matched).toBe(true);
    const updatedState = useThreePaneStudioStore.getState();
    expect(updatedState.selectedNodeId).toBe('res-server-config');
    expect(updatedState.highlightedNodeId).toBe('res-server-config');
    expect(updatedState.expandedNodeIds).toContain('root-workspace-resources');
    expect(updatedState.expandedNodeIds).toContain('res-server-config');

    const selectedNode = updatedState.getSelectedNode();
    expect(selectedNode?.status).toBe('reading');
    expect(selectedNode?.activeHighlight).toBe(true);
  });

  it('should return false when target path is not present in context tree', () => {
    const store = useThreePaneStudioStore.getState();
    const matched = store.triggerToolHighlight({
      toolName: 'read_file',
      targetPath: '/non/existent/path.ts',
      actionType: 'read',
      timestamp: 2000,
    });

    expect(matched).toBe(false);
    expect(useThreePaneStudioStore.getState().lastToolEvent?.targetPath).toBe('/non/existent/path.ts');
  });

  it('should clear highlight across all tree nodes', () => {
    const store = useThreePaneStudioStore.getState();
    store.clearHighlight();
    expect(useThreePaneStudioStore.getState().highlightedNodeId).toBeNull();
  });
});
