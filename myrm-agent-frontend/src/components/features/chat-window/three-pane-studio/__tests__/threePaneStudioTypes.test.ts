/**
 * [INPUT]
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioTypes
 *
 * [OUTPUT]
 * - Domain contracts and type assertion tests for Item 198.
 */

import { describe, it, expect } from 'vitest';
import type {
  ContextNodeType,
  NodeStatus,
  ContextTreeNode,
  StudioPaneLayout,
  RightPaneMode,
  ToolHighlightAction,
  ToolHighlightEvent,
  ThreePaneStudioStoreState,
} from '../threePaneStudioTypes';

describe('ThreePaneStudioTypes Contracts', () => {
  it('should accept valid ContextNodeType, NodeStatus, and RightPaneMode values', () => {
    const nodeTypes: ContextNodeType[] = ['user_memory', 'resource', 'skill'];
    expect(nodeTypes).toHaveLength(3);

    const statuses: NodeStatus[] = ['idle', 'reading', 'writing', 'modified'];
    expect(statuses).toHaveLength(4);

    const modes: RightPaneMode[] = ['agent_chat', 'terminal'];
    expect(modes).toHaveLength(2);

    const actions: ToolHighlightAction[] = ['read', 'write', 'inspect'];
    expect(actions).toHaveLength(3);
  });

  it('should construct a valid ContextTreeNode entity', () => {
    const childNode: ContextTreeNode = {
      id: 'res-child-1',
      label: 'App.tsx',
      type: 'resource',
      path: '/workspace/src/App.tsx',
      content: 'export const App = () => <div>Hello</div>;',
      status: 'idle',
      activeHighlight: false,
    };

    const rootNode: ContextTreeNode = {
      id: 'res-root',
      label: 'Workspace Resources',
      type: 'resource',
      path: '/workspace',
      children: [childNode],
    };

    expect(rootNode.id).toBe('res-root');
    expect(rootNode.children).toHaveLength(1);
    expect(rootNode.children?.[0].label).toBe('App.tsx');
  });

  it('should conform to ToolHighlightEvent and StudioPaneLayout contracts', () => {
    const event: ToolHighlightEvent = {
      toolName: 'read_file',
      targetPath: '/workspace/src/App.tsx',
      actionType: 'read',
      timestamp: 1760000000000,
      sessionId: 'sess-123',
    };

    const layout: StudioPaneLayout = {
      leftWidth: 280,
      rightWidth: 400,
      isLeftCollapsed: false,
      isRightCollapsed: false,
    };

    const state: ThreePaneStudioStoreState = {
      rootNodes: [],
      selectedNodeId: null,
      expandedNodeIds: [],
      highlightedNodeId: null,
      rightPaneMode: 'agent_chat',
      layout,
      lastToolEvent: event,
    };

    expect(event.toolName).toBe('read_file');
    expect(state.layout.leftWidth).toBe(280);
    expect(state.lastToolEvent?.sessionId).toBe('sess-123');
  });
});
