/**
 * [INPUT]
 * - None (Pure domain type definitions for Three-Pane Context Studio & Real-time Tool Highlight)
 *
 * [OUTPUT]
 * - ContextNodeType, NodeStatus, ContextTreeNode, StudioPaneLayout,
 *   RightPaneMode, ToolHighlightAction, ToolHighlightEvent, ThreePaneStudioStoreState
 *
 * [POS]
 * Unified domain contracts for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite.
 * Powers three-pane visual white-box studio with real-time tool-tree active highlighting,
 * seamless Agent-chat / Terminal toggling, and interactive context exploration.
 */

export type ContextNodeType = 'user_memory' | 'resource' | 'skill';

export type NodeStatus = 'idle' | 'reading' | 'writing' | 'modified';

export interface ContextTreeNode {
  readonly id: string;
  readonly label: string;
  readonly type: ContextNodeType;
  readonly path: string;
  readonly content?: string;
  readonly status?: NodeStatus;
  readonly children?: readonly ContextTreeNode[];
  readonly activeHighlight?: boolean;
  readonly metadata?: Readonly<Record<string, string | number | boolean>>;
}

export interface StudioPaneLayout {
  readonly leftWidth: number;
  readonly rightWidth: number;
  readonly isLeftCollapsed: boolean;
  readonly isRightCollapsed: boolean;
}

export type RightPaneMode = 'agent_chat' | 'terminal';

export type ToolHighlightAction = 'read' | 'write' | 'inspect';

export interface ToolHighlightEvent {
  readonly toolName: string;
  readonly targetPath: string;
  readonly actionType: ToolHighlightAction;
  readonly timestamp: number;
  readonly sessionId?: string;
}

export interface ThreePaneStudioStoreState {
  readonly rootNodes: readonly ContextTreeNode[];
  readonly selectedNodeId: string | null;
  readonly expandedNodeIds: readonly string[];
  readonly highlightedNodeId: string | null;
  readonly rightPaneMode: RightPaneMode;
  readonly layout: StudioPaneLayout;
  readonly lastToolEvent: ToolHighlightEvent | null;
}
