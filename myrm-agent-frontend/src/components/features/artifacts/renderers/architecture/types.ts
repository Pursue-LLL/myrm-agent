/**
 * Architecture IR Data Types & Protocols
 * Standard JSON IR for interactive architecture maps, workflows, and evolution diffs.
 */

export type ArchitectureDiagramType = 'architecture' | 'workflow' | 'sequence' | 'dataflow' | 'lifecycle';

export type NodeCategory =
  | 'frontend'
  | 'gateway'
  | 'backend'
  | 'database'
  | 'cache'
  | 'queue'
  | 'external'
  | 'security'
  | 'custom';

export type NodeStatus = 'healthy' | 'warning' | 'degraded' | 'offline';

export type DiffState = 'added' | 'deleted' | 'modified' | 'rerouted' | 'unchanged';

export interface ArchitectureNodeIR {
  id: string;
  label: string;
  group?: string;
  group_id?: string;
  type?: string;
  category?: NodeCategory;
  icon?: string;
  description?: string;
  status?: NodeStatus;
  technologies?: string[];
  tech_stack?: string;
  metrics?: Record<string, string>;
  // Diff metadata attached during evolution analysis
  diffState?: DiffState;
}

export interface ArchitectureGroupIR {
  id: string;
  label: string;
  style?: 'solid' | 'dashed';
}

export interface ArchitectureEdgeIR {
  id: string;
  source: string;
  target: string;
  label?: string;
  animated?: boolean;
  protocol?: string;
  style?: 'solid' | 'dashed';
  diffState?: DiffState;
}

export interface ArchitectureIR {
  version?: string;
  type?: ArchitectureDiagramType;
  diagram_type?: ArchitectureDiagramType;
  title?: string;
  description?: string;
  direction?: 'TB' | 'LR';
  groups?: ArchitectureGroupIR[];
  nodes: ArchitectureNodeIR[];
  edges: ArchitectureEdgeIR[];
}
