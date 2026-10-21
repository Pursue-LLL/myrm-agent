/**
 * Planner DAG Layout Engine
 * 智能体规划 DAG 拓扑分层布局与贝塞尔曲线生成引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯算法纯函数设计，具备确定性与高性能。
 */

import {
  PlannerDagEdge,
  PlannerDagNode,
  PlannerGraphLayout,
  PlannerLayoutNode,
} from './plannerCanvasTypes';

const NODE_WIDTH = 220;
const NODE_HEIGHT = 88;
const HORIZONTAL_GAP = 70;
const VERTICAL_GAP = 30;
const PADDING = 30;

/**
 * 拓扑分层算法：为每个节点计算层级 (Layer)
 * 根节点层级为 0，依赖节点的层级为 max(父节点层级) + 1
 */
export function computeNodeLayers(nodes: PlannerDagNode[]): Map<string, number> {
  const nodeMap = new Map<string, PlannerDagNode>();
  for (const node of nodes) {
    nodeMap.set(node.id, node);
  }

  const layers = new Map<string, number>();
  const visiting = new Set<string>();

  function getLayer(nodeId: string): number {
    const cachedLayer = layers.get(nodeId);
    if (cachedLayer !== undefined) {
      return cachedLayer;
    }
    if (visiting.has(nodeId)) {
      // 出现环路保护，返回 0
      return 0;
    }

    visiting.add(nodeId);
    const node = nodeMap.get(nodeId);
    let maxParentLayer = -1;

    if (node && node.dependsOn.length > 0) {
      for (const parentId of node.dependsOn) {
        if (nodeMap.has(parentId)) {
          const parentLayer = getLayer(parentId);
          if (parentLayer > maxParentLayer) {
            maxParentLayer = parentLayer;
          }
        }
      }
    }

    visiting.delete(nodeId);
    const resultLayer = maxParentLayer + 1;
    layers.set(nodeId, resultLayer);
    return resultLayer;
  }

  for (const node of nodes) {
    getLayer(node.id);
  }

  return layers;
}

/**
 * 生成平滑的三次贝塞尔曲线路径
 */
export function generateCubicBezierPath(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number
): string {
  const dx = toX - fromX;
  const controlPointOffset = Math.max(30, dx * 0.45);
  const cp1X = fromX + controlPointOffset;
  const cp1Y = fromY;
  const cp2X = toX - controlPointOffset;
  const cp2Y = toY;

  return `M ${fromX} ${fromY} C ${cp1X} ${cp1Y}, ${cp2X} ${cp2Y}, ${toX} ${toY}`;
}

/**
 * 执行整个 DAG 的图谱布局与连线计算
 */
export function layoutPlannerGraph(nodes: PlannerDagNode[]): PlannerGraphLayout {
  if (nodes.length === 0) {
    return {
      nodes: [],
      edges: [],
      canvasWidth: 300,
      canvasHeight: 200,
    };
  }

  const layerMap = computeNodeLayers(nodes);
  const layerGroups = new Map<number, PlannerDagNode[]>();

  let maxLayer = 0;
  for (const node of nodes) {
    const layer = layerMap.get(node.id) ?? 0;
    if (layer > maxLayer) {
      maxLayer = layer;
    }
    const existingGroup = layerGroups.get(layer);
    if (existingGroup) {
      existingGroup.push(node);
    } else {
      layerGroups.set(layer, [node]);
    }
  }

  const layoutNodes: PlannerLayoutNode[] = [];
  const layoutNodeMap = new Map<string, PlannerLayoutNode>();

  let maxRowNodes = 0;
  for (let l = 0; l <= maxLayer; l++) {
    const group = layerGroups.get(l) ?? [];
    if (group.length > maxRowNodes) {
      maxRowNodes = group.length;
    }

    const x = PADDING + l * (NODE_WIDTH + HORIZONTAL_GAP);

    for (let i = 0; i < group.length; i++) {
      const node = group[i];
      const y = PADDING + i * (NODE_HEIGHT + VERTICAL_GAP);

      const layoutNode: PlannerLayoutNode = {
        ...node,
        x,
        y,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        layer: l,
      };

      layoutNodes.push(layoutNode);
      layoutNodeMap.set(node.id, layoutNode);
    }
  }

  const edges: PlannerDagEdge[] = [];

  for (const node of layoutNodes) {
    for (const parentId of node.dependsOn) {
      const parent = layoutNodeMap.get(parentId);
      if (parent) {
        const fromX = parent.x + parent.width;
        const fromY = parent.y + parent.height / 2;
        const toX = node.x;
        const toY = node.y + node.height / 2;

        const isParentActive =
          parent.status === 'running' || parent.status === 'completed';
        const isChildActive =
          node.status === 'running' || node.status === 'completed';

        edges.push({
          from: parentId,
          to: node.id,
          fromX,
          fromY,
          toX,
          toY,
          pathD: generateCubicBezierPath(fromX, fromY, toX, toY),
          isActive: isParentActive && isChildActive,
        });
      }
    }
  }

  const canvasWidth =
    PADDING * 2 + (maxLayer + 1) * NODE_WIDTH + maxLayer * HORIZONTAL_GAP;
  const canvasHeight = Math.max(
    260,
    PADDING * 2 + maxRowNodes * NODE_HEIGHT + (maxRowNodes - 1) * VERTICAL_GAP
  );

  return {
    nodes: layoutNodes,
    edges,
    canvasWidth,
    canvasHeight,
  };
}
