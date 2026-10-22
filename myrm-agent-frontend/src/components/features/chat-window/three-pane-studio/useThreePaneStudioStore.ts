/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioTypes
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioEngine
 *
 * [OUTPUT]
 * - useThreePaneStudioStore (POS: Central reactive store for Three-Pane Context Studio)
 *
 * [POS]
 * Central reactive dispatcher for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite.
 * Coordinates context tree state, tool-driven active highlighting, ancestor auto-unfolding,
 * middle-pane file loading, and right-pane Agent-chat/Terminal view toggling.
 */

import { create } from 'zustand';
import type {
  ThreePaneStudioStoreState,
  ContextTreeNode,
  RightPaneMode,
  StudioPaneLayout,
  ToolHighlightEvent,
  NodeStatus,
} from './threePaneStudioTypes';
import {
  findNodeById,
  findNodeByPath,
  findAncestorNodeIds,
  updateNodeStatusAndHighlight,
  buildDefaultContextTree,
} from './threePaneStudioEngine';

export interface ThreePaneStudioStoreActions {
  readonly setRootNodes: (nodes: readonly ContextTreeNode[]) => void;
  readonly selectNode: (nodeId: string | null) => void;
  readonly toggleNodeExpanded: (nodeId: string, expand?: boolean) => void;
  readonly setRightPaneMode: (mode: RightPaneMode) => void;
  readonly setPaneLayout: (partial: Partial<StudioPaneLayout>) => void;
  readonly toggleLeftCollapse: () => void;
  readonly toggleRightCollapse: () => void;
  readonly triggerToolHighlight: (event: ToolHighlightEvent) => boolean;
  readonly clearHighlight: () => void;
  readonly getSelectedNode: () => ContextTreeNode | null;
  readonly resetStore: () => void;
}

export type ThreePaneStudioStore = ThreePaneStudioStoreState & ThreePaneStudioStoreActions;

const initialLayout: StudioPaneLayout = {
  leftWidth: 260,
  rightWidth: 380,
  isLeftCollapsed: false,
  isRightCollapsed: false,
};

const initialState: ThreePaneStudioStoreState = {
  rootNodes: buildDefaultContextTree(),
  selectedNodeId: null,
  expandedNodeIds: ['root-workspace-resources'],
  highlightedNodeId: null,
  rightPaneMode: 'agent_chat',
  layout: initialLayout,
  lastToolEvent: null,
};

export const useThreePaneStudioStore = create<ThreePaneStudioStore>((set, get) => ({
  ...initialState,

  setRootNodes: (nodes: readonly ContextTreeNode[]) => {
    set({ rootNodes: nodes });
  },

  selectNode: (nodeId: string | null) => {
    set({ selectedNodeId: nodeId });
  },

  toggleNodeExpanded: (nodeId: string, expand?: boolean) => {
    set((state) => {
      const isCurrentlyExpanded = state.expandedNodeIds.includes(nodeId);
      const shouldExpand = typeof expand === 'boolean' ? expand : !isCurrentlyExpanded;

      if (shouldExpand) {
        return {
          expandedNodeIds: isCurrentlyExpanded
            ? state.expandedNodeIds
            : [...state.expandedNodeIds, nodeId],
        };
      }
      return {
        expandedNodeIds: state.expandedNodeIds.filter((id) => id !== nodeId),
      };
    });
  },

  setRightPaneMode: (mode: RightPaneMode) => {
    set({ rightPaneMode: mode });
  },

  setPaneLayout: (partial: Partial<StudioPaneLayout>) => {
    set((state) => ({
      layout: {
        ...state.layout,
        ...partial,
      },
    }));
  },

  toggleLeftCollapse: () => {
    set((state) => ({
      layout: {
        ...state.layout,
        isLeftCollapsed: !state.layout.isLeftCollapsed,
      },
    }));
  },

  toggleRightCollapse: () => {
    set((state) => ({
      layout: {
        ...state.layout,
        isRightCollapsed: !state.layout.isRightCollapsed,
      },
    }));
  },

  triggerToolHighlight: (event: ToolHighlightEvent) => {
    const { rootNodes, expandedNodeIds } = get();
    const matchedNode = findNodeByPath(rootNodes, event.targetPath);

    if (!matchedNode) {
      set({ lastToolEvent: event });
      return false;
    }

    const ancestors = findAncestorNodeIds(rootNodes, matchedNode.id);
    const newExpanded = Array.from(new Set([...expandedNodeIds, ...ancestors, matchedNode.id]));

    const nodeStatus: NodeStatus = event.actionType === 'write' ? 'writing' : 'reading';
    const updatedNodes = updateNodeStatusAndHighlight(
      rootNodes,
      matchedNode.id,
      nodeStatus,
      true,
    );

    set({
      rootNodes: updatedNodes,
      expandedNodeIds: newExpanded,
      selectedNodeId: matchedNode.id,
      highlightedNodeId: matchedNode.id,
      lastToolEvent: event,
    });

    return true;
  },

  clearHighlight: () => {
    const { rootNodes } = get();
    const cleared = updateNodeStatusAndHighlight(rootNodes, '', 'idle', false);
    set({
      rootNodes: cleared,
      highlightedNodeId: null,
    });
  },

  getSelectedNode: () => {
    const { rootNodes, selectedNodeId } = get();
    if (!selectedNodeId) {
      return null;
    }
    return findNodeById(rootNodes, selectedNodeId);
  },

  resetStore: () => {
    set({ ...initialState, rootNodes: buildDefaultContextTree() });
  },
}));
