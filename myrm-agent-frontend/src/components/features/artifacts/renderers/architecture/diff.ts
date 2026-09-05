import type { ArchitectureIR, ArchitectureNodeIR, ArchitectureEdgeIR } from './types';

/**
 * Computes semantic diff between two Architecture IR snapshots (before vs after).
 * Flags added, deleted, modified nodes, and rerouted or new edges.
 */
export function computeArchitectureDiff(before: ArchitectureIR, after: ArchitectureIR): ArchitectureIR {
  const beforeNodes = new Map<string, ArchitectureNodeIR>(before.nodes.map((n) => [n.id, n]));
  const afterNodes = new Map<string, ArchitectureNodeIR>(after.nodes.map((n) => [n.id, n]));

  const mergedNodes: ArchitectureNodeIR[] = [];

  // 1. Process After nodes (added or modified or unchanged)
  for (const [id, afterNode] of afterNodes.entries()) {
    const beforeNode = beforeNodes.get(id);
    if (!beforeNode) {
      mergedNodes.push({ ...afterNode, diffState: 'added' });
    } else {
      const isModified =
        beforeNode.label !== afterNode.label ||
        beforeNode.category !== afterNode.category ||
        beforeNode.group !== afterNode.group ||
        beforeNode.description !== afterNode.description;
      mergedNodes.push({
        ...afterNode,
        diffState: isModified ? 'modified' : 'unchanged',
      });
    }
  }

  // 2. Process Before nodes that were deleted in After
  for (const [id, beforeNode] of beforeNodes.entries()) {
    if (!afterNodes.has(id)) {
      mergedNodes.push({
        ...beforeNode,
        diffState: 'deleted',
      });
    }
  }

  // 3. Process Edges
  const beforeEdges = new Map<string, ArchitectureEdgeIR>(
    before.edges.map((e) => [`${e.source}->${e.target}`, e]),
  );
  const afterEdges = new Map<string, ArchitectureEdgeIR>(
    after.edges.map((e) => [`${e.source}->${e.target}`, e]),
  );

  const mergedEdges: ArchitectureEdgeIR[] = [];

  for (const [key, afterEdge] of afterEdges.entries()) {
    if (!beforeEdges.has(key)) {
      mergedEdges.push({ ...afterEdge, diffState: 'added', animated: true });
    } else {
      mergedEdges.push({ ...afterEdge, diffState: 'unchanged' });
    }
  }

  for (const [key, beforeEdge] of beforeEdges.entries()) {
    if (!afterEdges.has(key)) {
      mergedEdges.push({
        ...beforeEdge,
        id: `del-${beforeEdge.id || `${beforeEdge.source}-${beforeEdge.target}`}`,
        diffState: 'deleted',
        style: 'dashed',
      });
    }
  }

  return {
    ...after,
    title: after.title ? `${after.title} (Evolution Diff)` : 'Architecture Evolution Diff',
    nodes: mergedNodes,
    edges: mergedEdges,
  };
}
