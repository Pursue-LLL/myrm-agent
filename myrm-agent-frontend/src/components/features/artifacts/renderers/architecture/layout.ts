import dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/react';
import type { ArchitectureIR, ArchitectureNodeIR } from './types';

const NODE_WIDTH = 220;
const NODE_HEIGHT = 80;

export interface LayoutedElements {
  nodes: Node[];
  edges: Edge[];
}

/**
 * Validates and repairs architecture topology before layout:
 * 1. Deduplicates nodes
 * 2. Prunes invalid edges referencing nonexistent source or target
 */
export function sanitizeArchitectureIR(raw: ArchitectureIR): ArchitectureIR {
  const nodeMap = new Map<string, ArchitectureNodeIR>();
  for (const n of raw.nodes || []) {
    if (n && n.id && !nodeMap.has(n.id)) {
      const rawNode = n as Record<string, unknown>;
      const normalizedCategory = (n.category || rawNode.type || 'backend') as ArchitectureNodeIR['category'];
      const normalizedGroup = (n.group || rawNode.group_id) as string | undefined;
      const normalizedTech = n.technologies || (rawNode.tech_stack ? [String(rawNode.tech_stack)] : undefined);

      nodeMap.set(n.id, {
        ...n,
        category: normalizedCategory,
        group: normalizedGroup,
        technologies: normalizedTech,
      });
    }
  }

  const validNodes = Array.from(nodeMap.values());
  const validEdges = (raw.edges || [])
    .filter((e) => e && e.source && e.target && nodeMap.has(e.source) && nodeMap.has(e.target))
    .map((e, idx) => ({
      ...e,
      id: e.id || `edge-${e.source}-${e.target}-${idx}`,
    }));

  return {
    ...raw,
    nodes: validNodes,
    edges: validEdges,
  };
}

/**
 * Computes deterministic hierarchical DAG layout via Dagre
 */
export function computeDagreLayout(ir: ArchitectureIR): LayoutedElements {
  const cleanIR = sanitizeArchitectureIR(ir);
  const isHorizontal = cleanIR.direction === 'LR';

  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: isHorizontal ? 'LR' : 'TB',
    nodesep: 40,
    ranksep: 60,
    marginx: 30,
    marginy: 30,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of cleanIR.nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  for (const edge of cleanIR.edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const flowNodes: Node[] = cleanIR.nodes.map((node) => {
    const nodeWithPos = g.node(node.id);
    return {
      id: node.id,
      type: 'archNode',
      position: {
        x: nodeWithPos ? nodeWithPos.x - NODE_WIDTH / 2 : 0,
        y: nodeWithPos ? nodeWithPos.y - NODE_HEIGHT / 2 : 0,
      },
      data: {
        ...node,
      },
    };
  });

  const flowEdges: Edge[] = cleanIR.edges.map((edge) => {
    let strokeColor = undefined;
    if (edge.diffState === 'added') strokeColor = '#10b981'; // emerald-500
    if (edge.diffState === 'deleted') strokeColor = '#f43f5e'; // rose-500
    if (edge.diffState === 'rerouted') strokeColor = '#3b82f6'; // blue-500

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      animated: edge.animated ?? (edge.diffState === 'added'),
      type: 'smoothstep',
      data: {
        diffState: edge.diffState,
        protocol: edge.protocol,
      },
      style: {
        strokeWidth: edge.diffState && edge.diffState !== 'unchanged' ? 2.5 : 1.5,
        stroke: strokeColor,
        strokeDasharray: edge.diffState === 'deleted' ? '5,5' : undefined,
      },
    };
  });

  return { nodes: flowNodes, edges: flowEdges };
}
