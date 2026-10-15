import { describe, it, expect } from 'vitest';
import {
  computeRadialPositions,
  computeStringHash,
  computeTimeBuckets,
  DEFAULT_RADIAL_CONFIG,
  getCutoffTimestamp,
} from '../starMapRadialMath';
import { StarMapNode } from '../starMapTypes';

describe('starMapRadialMath pure functions', () => {
  it('computes consistent positive hash values for strings', () => {
    const hash1 = computeStringHash('skill-ts-clean-arch');
    const hash2 = computeStringHash('skill-ts-clean-arch');
    const hash3 = computeStringHash('mem-dialog-open-a11y');

    expect(hash1).toBe(hash2);
    expect(hash1).toBeGreaterThanOrEqual(0);
    expect(hash1).not.toBe(hash3);
  });

  it('handles empty node collections gracefully in coordinate and bucket calculations', () => {
    expect(computeRadialPositions([])).toEqual([]);
    expect(computeTimeBuckets([])).toEqual([]);
    expect(getCutoffTimestamp([], 0.5)).toBeDefined();
  });

  it('maps oldest node to inner radius and newest node to outer radius', () => {
    const mockNodes: StarMapNode[] = [
      {
        id: 'node-old',
        type: 'memory',
        name: '早期记忆',
        summary: '最早沉淀',
        createdAt: 1000,
        recallCount: 1,
        scope: 'global',
        tags: [],
      },
      {
        id: 'node-mid',
        type: 'skill',
        name: '中期技能',
        summary: '中期掌握',
        createdAt: 2000,
        recallCount: 5,
        scope: 'global',
        tags: [],
      },
      {
        id: 'node-new',
        type: 'skill',
        name: '最新技能',
        summary: '刚刚学会',
        createdAt: 3000,
        recallCount: 2,
        scope: 'agent-specific',
        tags: [],
      },
    ];

    const positioned = computeRadialPositions(mockNodes, DEFAULT_RADIAL_CONFIG);

    expect(positioned.length).toBe(3);
    const oldNode = positioned.find((n) => n.id === 'node-old');
    const midNode = positioned.find((n) => n.id === 'node-mid');
    const newNode = positioned.find((n) => n.id === 'node-new');

    expect(oldNode?.radialPosition?.r).toBe(DEFAULT_RADIAL_CONFIG.innerRadius);
    expect(newNode?.radialPosition?.r).toBe(DEFAULT_RADIAL_CONFIG.outerRadius);
    expect(midNode?.radialPosition?.r).toBe(
      DEFAULT_RADIAL_CONFIG.innerRadius +
        (DEFAULT_RADIAL_CONFIG.outerRadius - DEFAULT_RADIAL_CONFIG.innerRadius) * 0.5
    );

    // Verify Cartesian coordinates
    expect(oldNode?.radialPosition?.x).toBeDefined();
    expect(oldNode?.radialPosition?.y).toBeDefined();
  });

  it('computes time buckets with skill and memory breakdown', () => {
    const mockNodes: StarMapNode[] = [
      {
        id: 'n1',
        type: 'skill',
        name: 'S1',
        summary: '',
        createdAt: 1000,
        recallCount: 0,
        scope: 'global',
        tags: [],
      },
      {
        id: 'n2',
        type: 'memory',
        name: 'M1',
        summary: '',
        createdAt: 1000,
        recallCount: 0,
        scope: 'global',
        tags: [],
      },
      {
        id: 'n3',
        type: 'skill',
        name: 'S2',
        summary: '',
        createdAt: 5000,
        recallCount: 0,
        scope: 'global',
        tags: [],
      },
    ];

    const buckets = computeTimeBuckets(mockNodes, 4);

    expect(buckets.length).toBe(4);
    const totalSkills = buckets.reduce((sum, b) => sum + b.skillCount, 0);
    const totalMemories = buckets.reduce((sum, b) => sum + b.memoryCount, 0);

    expect(totalSkills).toBe(2);
    expect(totalMemories).toBe(1);
  });

  it('computes cutoff timestamp correctly based on playback progress', () => {
    const mockNodes: StarMapNode[] = [
      {
        id: 'n-start',
        type: 'skill',
        name: 'S-Start',
        summary: '',
        createdAt: 10000,
        recallCount: 0,
        scope: 'global',
        tags: [],
      },
      {
        id: 'n-end',
        type: 'memory',
        name: 'M-End',
        summary: '',
        createdAt: 20000,
        recallCount: 0,
        scope: 'global',
        tags: [],
      },
    ];

    expect(getCutoffTimestamp(mockNodes, 0.0)).toBe(10000);
    expect(getCutoffTimestamp(mockNodes, 0.5)).toBe(15000);
    expect(getCutoffTimestamp(mockNodes, 1.0)).toBe(20000);
    // Clamping test
    expect(getCutoffTimestamp(mockNodes, -0.2)).toBe(10000);
    expect(getCutoffTimestamp(mockNodes, 1.5)).toBe(20000);
  });
});
