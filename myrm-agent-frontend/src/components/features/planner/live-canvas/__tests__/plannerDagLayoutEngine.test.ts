import { describe, it, expect } from 'vitest';
import {
  computeNodeLayers,
  generateCubicBezierPath,
  layoutPlannerGraph,
} from '../plannerDagLayoutEngine';
import { PlannerDagNode } from '../plannerCanvasTypes';

describe('plannerDagLayoutEngine', () => {
  describe('computeNodeLayers', () => {
    it('正确为无前置依赖的根节点分配 layer 0', () => {
      const nodes: PlannerDagNode[] = [
        { id: 'node-1', title: 'Task 1', status: 'pending', dependsOn: [] },
        { id: 'node-2', title: 'Task 2', status: 'pending', dependsOn: [] },
      ];

      const layers = computeNodeLayers(nodes);
      expect(layers.get('node-1')).toBe(0);
      expect(layers.get('node-2')).toBe(0);
    });

    it('沿依赖链逐级递增计算层级', () => {
      const nodes: PlannerDagNode[] = [
        { id: 'step-a', title: 'Step A', status: 'completed', dependsOn: [] },
        { id: 'step-b', title: 'Step B', status: 'completed', dependsOn: ['step-a'] },
        { id: 'step-c', title: 'Step C', status: 'running', dependsOn: ['step-b'] },
      ];

      const layers = computeNodeLayers(nodes);
      expect(layers.get('step-a')).toBe(0);
      expect(layers.get('step-b')).toBe(1);
      expect(layers.get('step-c')).toBe(2);
    });

    it('多父节点依赖时取父节点的最大层级加一', () => {
      const nodes: PlannerDagNode[] = [
        { id: 'root-1', title: 'Root 1', status: 'completed', dependsOn: [] },
        { id: 'root-2', title: 'Root 2', status: 'completed', dependsOn: [] },
        { id: 'mid', title: 'Mid', status: 'completed', dependsOn: ['root-1'] },
        { id: 'join', title: 'Join', status: 'pending', dependsOn: ['root-2', 'mid'] },
      ];

      const layers = computeNodeLayers(nodes);
      expect(layers.get('mid')).toBe(1);
      expect(layers.get('join')).toBe(2);
    });
  });

  describe('generateCubicBezierPath', () => {
    it('生成标准 SVG 三次贝塞尔曲线路径字符串', () => {
      const path = generateCubicBezierPath(100, 50, 300, 150);
      expect(path).toMatch(/^M 100 50 C/);
      expect(path).toContain('300 150');
    });
  });

  describe('layoutPlannerGraph', () => {
    it('当节点列表为空时返回安全的兜底默认画布宽高', () => {
      const layout = layoutPlannerGraph([]);
      expect(layout.nodes).toEqual([]);
      expect(layout.edges).toEqual([]);
      expect(layout.canvasWidth).toBe(300);
      expect(layout.canvasHeight).toBe(200);
    });

    it('正确计算各个节点的定位坐标与连接边', () => {
      const nodes: PlannerDagNode[] = [
        { id: 'n1', title: 'Node 1', status: 'completed', dependsOn: [] },
        { id: 'n2', title: 'Node 2', status: 'running', dependsOn: ['n1'] },
      ];

      const layout = layoutPlannerGraph(nodes);
      expect(layout.nodes.length).toBe(2);
      expect(layout.edges.length).toBe(1);

      const n1 = layout.nodes.find((n) => n.id === 'n1');
      const n2 = layout.nodes.find((n) => n.id === 'n2');
      expect(n1).toBeDefined();
      expect(n2).toBeDefined();

      if (n1 && n2) {
        // n2 位于 n1 右侧 (x 更大)
        expect(n2.x).toBeGreaterThan(n1.x);
      }

      // 边从 n1 连接到 n2，且因 n1 完成且 n2 运行中，isActive 为 true
      const edge = layout.edges[0];
      expect(edge.from).toBe('n1');
      expect(edge.to).toBe('n2');
      expect(edge.isActive).toBe(true);
      expect(edge.pathD).toContain('M');
    });
  });
});
