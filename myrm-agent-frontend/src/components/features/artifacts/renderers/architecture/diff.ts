/**
 * [INPUT]
 * - architecture/types::ArchitectureIR, ArchitectureNodeIR, ArchitectureEdgeIR, DiffSummary
 *
 * [OUTPUT]
 * - computeArchitectureDiff: 架构拓扑语义对比与演进差异量化计算函数
 *
 * [POS]
 * Architecture Evolution Diff Engine — 增量计算两份架构快照的结构语义差异与指标汇总。
 */
import type { ArchitectureIR, ArchitectureNodeIR, ArchitectureEdgeIR, DiffSummary } from './types';

/**
 * Computes semantic diff between two Architecture IR snapshots (before vs after).
 * Flags added, deleted, modified nodes, and rerouted or new edges.
 */
export function computeArchitectureDiff(before: ArchitectureIR, after: ArchitectureIR): ArchitectureIR {
  const beforeNodes = new Map<string, ArchitectureNodeIR>(before.nodes.map((n) => [n.id, n]));
  const afterNodes = new Map<string, ArchitectureNodeIR>(after.nodes.map((n) => [n.id, n]));

  const mergedNodes: ArchitectureNodeIR[] = [];
  let addedNodes = 0;
  let modifiedNodes = 0;
  let deletedNodes = 0;

  // 1. Process After nodes (added or modified or unchanged)
  for (const [id, afterNode] of afterNodes.entries()) {
    const beforeNode = beforeNodes.get(id);
    if (!beforeNode) {
      mergedNodes.push({ ...afterNode, diffState: 'added' });
      addedNodes += 1;
    } else {
      const techBefore = (beforeNode.technologies || []).join(',');
      const techAfter = (afterNode.technologies || []).join(',');
      const isModified =
        beforeNode.label !== afterNode.label ||
        beforeNode.category !== afterNode.category ||
        beforeNode.group !== afterNode.group ||
        beforeNode.description !== afterNode.description ||
        beforeNode.status !== afterNode.status ||
        techBefore !== techAfter;
      if (isModified) {
        modifiedNodes += 1;
      }
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
      deletedNodes += 1;
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
  let addedEdges = 0;
  let deletedEdges = 0;

  for (const [key, afterEdge] of afterEdges.entries()) {
    if (!beforeEdges.has(key)) {
      mergedEdges.push({ ...afterEdge, diffState: 'added', animated: true });
      addedEdges += 1;
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
      deletedEdges += 1;
    }
  }

  const diffSummary: DiffSummary = {
    addedNodes,
    deletedNodes,
    modifiedNodes,
    addedEdges,
    deletedEdges,
  };

  return {
    ...after,
    title: after.title ? `${after.title} (Evolution Diff)` : 'Architecture Evolution Diff',
    nodes: mergedNodes,
    edges: mergedEdges,
    diffSummary,
  };
}
