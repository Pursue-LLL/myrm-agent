/**
 * [INPUT] @/services/memory/commandCenter::MemoryCommandGraphNode, MemoryCommandGraphResponse (POS: 命令中心图谱数据契约)
 * [OUTPUT] ForceNode / ForceLink / ForceGraphData: 力导向图数据结构；REL_COLORS / NODE_COLORS 与 getNodeColor / getLinkColor / getNodeRadius / getNodeDisplayName / nodeId / toForceGraph: 配色、尺寸、显示名与响应转换
 * [POS] MemoryKnowledgeGraph 的纯数据层：不含 React 与 DOM，主视图与图例共用同一套配色口径。
 */

import { type MemoryCommandGraphNode, type MemoryCommandGraphResponse } from '@/services/memory/commandCenter';

export interface ForceNode extends MemoryCommandGraphNode {
  x?: number;
  y?: number;
  __indexColor?: string;
}

export interface ForceLink {
  source: string | ForceNode;
  target: string | ForceNode;
  rel_type: string;
  id: string;
  properties: Record<string, string | number>;
}

export interface ForceGraphData {
  nodes: ForceNode[];
  links: ForceLink[];
}

export const REL_COLORS: Record<string, string> = {
  SUPPORTED_BY: '#10b981',
  CONTRADICTED_BY: '#ef4444',
  SUPERSEDED_BY: '#f59e0b',
  CONSTRAINED_BY: '#3b82f6',
};
export const REL_KEYS = Object.keys(REL_COLORS);
const DEFAULT_LINK_COLOR = '#6b7280';

export const NODE_COLORS: Record<string, string> = {
  Claim: '#8b5cf6',
  Evidence: '#64748b',
};
const DEFAULT_NODE_COLOR = '#a1a1aa';

export const getNodeColor = (labels: string[]): string =>
  labels.includes('Claim')
    ? NODE_COLORS.Claim
    : labels.includes('Evidence')
      ? NODE_COLORS.Evidence
      : DEFAULT_NODE_COLOR;

export const getLinkColor = (relType: string): string => REL_COLORS[relType] ?? DEFAULT_LINK_COLOR;

export const getNodeRadius = (labels: string[]): number => (labels.includes('Claim') ? 6 : 4);

export const nodeId = (n: string | ForceNode): string => (typeof n === 'string' ? n : n.id);

export const toForceGraph = (resp: MemoryCommandGraphResponse): ForceGraphData => ({
  nodes: resp.nodes.map((n) => ({ ...n })),
  links: resp.edges.map((e) => ({
    source: e.source,
    target: e.target,
    rel_type: e.rel_type,
    id: e.id,
    properties: e.properties,
  })),
});

export const getNodeDisplayName = (node: ForceNode): string => {
  const props = node.properties;
  if (typeof props.content === 'string' && props.content.length > 0) {
    return props.content.length > 60 ? `${props.content.slice(0, 57)}…` : props.content;
  }
  if (typeof props.name === 'string') {
    return props.name;
  }
  return node.labels[0] ?? node.id.slice(0, 8);
};
