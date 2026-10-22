/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - GraphLayerType, NodeStatus, GraphNode, GraphEdge, QuadGraphModel, NodeSteerPayload, etc.
 *
 * [POS]
 * Domain types for QuadGraphMultiLayerExecutionCanvasAndTopologyInspectionHUD (Item 50 P0).
 * Strictly under 100 lines. Zero `any`.
 */

export type GraphLayerType = 'task' | 'workflow' | 'team' | 'communication';

export type NodeStatus = 'pending' | 'running' | 'verifying' | 'completed' | 'failed';

export interface GraphNode {
  id: string;
  label: string;
  layer: GraphLayerType;
  status: NodeStatus;
  role?: string;
  durationMs?: number;
  inputSnapshot?: string;
  outputSnapshot?: string;
  error?: string;
  dependencies?: string[];
  x?: number;
  y?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  layer: GraphLayerType;
  label?: string;
  active?: boolean;
  flowCount?: number;
}

export interface QuadGraphSummary {
  totalNodes: number;
  totalEdges: number;
  completedNodes: number;
  runningNodes: number;
  failedNodes: number;
  totalDurationMs: number;
}

export interface QuadGraphModel {
  sessionId?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface NodeSteerPayload {
  nodeId: string;
  instruction: string;
  action: 'steer' | 'pause' | 'resume' | 'retry';
}

export interface QuadGraphExecutionCanvasProps {
  model?: QuadGraphModel;
  activeLayer?: GraphLayerType;
  className?: string;
  onSteerNode?: (payload: NodeSteerPayload) => void;
}

export interface GraphViewportSwitcherProps {
  activeLayer: GraphLayerType;
  onSelectLayer: (layer: GraphLayerType) => void;
  nodeCountsByLayer?: Record<GraphLayerType, number>;
  className?: string;
}

export interface NodeInspectionDrawerProps {
  node: GraphNode | null;
  isOpen: boolean;
  onClose: () => void;
  onSteerNode?: (payload: NodeSteerPayload) => void;
  className?: string;
}
