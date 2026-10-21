import { describe, it, expect } from 'vitest';
import {
  computeSpeculativeLatency,
  formatElapsedMs,
  analyzeCriticalPathProgress,
  groupStepsByParallelBatch,
} from '../ttftDecouplingEngine';
import { DagStepNode } from '../ttftDecouplingTypes';

describe('ttftDecouplingEngine', () => {
  describe('computeSpeculativeLatency', () => {
    it('calculates latency correctly with fallback minimum of 10ms', () => {
      const now = 10000;
      expect(computeSpeculativeLatency(9850, now)).toBe(150);
      expect(computeSpeculativeLatency(9995, now)).toBe(10);
    });
  });

  describe('formatElapsedMs', () => {
    it('formats millisecond values under 1000ms', () => {
      expect(formatElapsedMs(0)).toBe('0ms');
      expect(formatElapsedMs(185)).toBe('185ms');
      expect(formatElapsedMs(999)).toBe('999ms');
    });

    it('formats second values for 1000ms and above', () => {
      expect(formatElapsedMs(1000)).toBe('1.0s');
      expect(formatElapsedMs(2450)).toBe('2.5s');
      expect(formatElapsedMs(12800)).toBe('12.8s');
    });
  });

  describe('analyzeCriticalPathProgress', () => {
    it('returns zeroes when steps list is empty', () => {
      const res = analyzeCriticalPathProgress([]);
      expect(res.totalSteps).toBe(0);
      expect(res.completedSteps).toBe(0);
      expect(res.criticalPathTotal).toBe(0);
      expect(res.progressPercent).toBe(0);
      expect(res.isCriticalPathBlocked).toBe(false);
    });

    it('correctly calculates completed count and critical path progress', () => {
      const steps: DagStepNode[] = [
        {
          id: 's1',
          name: '步骤1',
          status: 'completed',
          isCriticalPath: true,
        },
        {
          id: 's2',
          name: '步骤2',
          status: 'completed',
          isCriticalPath: false,
        },
        {
          id: 's3',
          name: '步骤3',
          status: 'running',
          isCriticalPath: true,
        },
        {
          id: 's4',
          name: '步骤4',
          status: 'pending',
          isCriticalPath: true,
        },
      ];

      const res = analyzeCriticalPathProgress(steps);
      expect(res.totalSteps).toBe(4);
      expect(res.completedSteps).toBe(2);
      expect(res.criticalPathTotal).toBe(3);
      expect(res.criticalPathCompleted).toBe(1);
      expect(res.progressPercent).toBe(50);
      expect(res.isCriticalPathBlocked).toBe(false);
    });

    it('marks critical path as blocked if any critical step fails', () => {
      const steps: DagStepNode[] = [
        {
          id: 's1',
          name: '核心规划',
          status: 'failed',
          isCriticalPath: true,
        },
      ];

      const res = analyzeCriticalPathProgress(steps);
      expect(res.isCriticalPathBlocked).toBe(true);
    });
  });

  describe('groupStepsByParallelBatch', () => {
    it('groups contiguous steps with the same parallelGroupId', () => {
      const steps: DagStepNode[] = [
        { id: '1', name: '初始化', status: 'completed', isCriticalPath: true },
        {
          id: '2',
          name: '查库存',
          status: 'running',
          parallelGroupId: 'p1',
          isCriticalPath: false,
        },
        {
          id: '3',
          name: '查积分',
          status: 'running',
          parallelGroupId: 'p1',
          isCriticalPath: false,
        },
        { id: '4', name: '下单', status: 'pending', isCriticalPath: true },
      ];

      const groups = groupStepsByParallelBatch(steps);
      expect(groups.length).toBe(3);
      expect(groups[0]?.isParallel).toBe(false);
      expect(groups[0]?.nodes[0]?.id).toBe('1');

      expect(groups[1]?.isParallel).toBe(true);
      expect(groups[1]?.groupId).toBe('p1');
      expect(groups[1]?.nodes.length).toBe(2);

      expect(groups[2]?.isParallel).toBe(false);
      expect(groups[2]?.nodes[0]?.id).toBe('4');
    });
  });
});
