/**
 * [INPUT] None (Foundation types for multi-type deliverable inspection and selective patching)
 * [OUTPUT] DeliverableNode, DeliverableSnapshot, SelectivePatchRequest, SnapshotDiffItem contracts
 * [POS] artifacts/deliverable-inspector/deliverableInspectorTypes.ts
 */

export type DeliverableType = 'slides' | 'document' | 'spreadsheet' | 'markdown';

export type DeliverableNodeType = 'slide' | 'section' | 'sheet';

export interface DeliverableNode {
  id: string;
  index: number;
  title: string;
  summary: string;
  nodeType: DeliverableNodeType;
  content: string;
  metadata?: Record<string, string | number | boolean>;
}

export type PatchMode = 'regenerate_node' | 'refine_content' | 'tweak_style';

export interface SelectivePatchRequest {
  nodeId: string;
  targetedPrompt: string;
  patchMode: PatchMode;
}

export interface DeliverableSnapshot {
  version: number;
  timestamp: number;
  deliverableType: DeliverableType;
  nodes: DeliverableNode[];
  changeDescription?: string;
  patchedNodeId?: string;
}

export type DiffChangeStatus = 'unchanged' | 'modified' | 'added' | 'removed';

export interface SnapshotDiffItem {
  nodeId: string;
  nodeTitle: string;
  status: DiffChangeStatus;
  beforeContent?: string;
  afterContent?: string;
}
