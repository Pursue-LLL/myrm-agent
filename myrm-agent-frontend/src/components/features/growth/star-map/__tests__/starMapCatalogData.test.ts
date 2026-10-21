import { describe, it, expect } from 'vitest';
import {
  filterStarMapLinks,
  filterStarMapNodes,
  INITIAL_STAR_MAP_LINKS,
  INITIAL_STAR_MAP_NODES,
} from '../starMapCatalogData';
import { StarMapFilter, StarMapNode } from '../starMapTypes';

describe('starMapCatalogData pure functions', () => {
  const defaultFilter: StarMapFilter = {
    scope: 'all',
    type: 'all',
    agentScope: 'all',
    timeSpan: 'all',
    hideLabels: false,
  };

  it('filters nodes by recall usage scope', () => {
    const nodesWithZeroRecall: StarMapNode[] = [
      ...INITIAL_STAR_MAP_NODES,
      {
        id: 'unused-node',
        type: 'skill',
        name: '未使用的技能',
        summary: '',
        createdAt: Date.now(),
        recallCount: 0,
        scope: 'global',
        tags: [],
      },
    ];

    const usedNodes = filterStarMapNodes(nodesWithZeroRecall, {
      ...defaultFilter,
      scope: 'used',
    });

    expect(usedNodes.every((n) => n.recallCount > 0)).toBe(true);
    expect(usedNodes.some((n) => n.id === 'unused-node')).toBe(false);
  });

  it('filters nodes by entity type (skill vs memory)', () => {
    const skillsOnly = filterStarMapNodes(INITIAL_STAR_MAP_NODES, {
      ...defaultFilter,
      type: 'skill',
    });
    expect(skillsOnly.every((n) => n.type === 'skill')).toBe(true);
    expect(skillsOnly.length).toBeGreaterThan(0);

    const memoriesOnly = filterStarMapNodes(INITIAL_STAR_MAP_NODES, {
      ...defaultFilter,
      type: 'memory',
    });
    expect(memoriesOnly.every((n) => n.type === 'memory')).toBe(true);
    expect(memoriesOnly.length).toBeGreaterThan(0);
  });

  it('filters nodes by agent scope (global vs agent-specific)', () => {
    const globalNodes = filterStarMapNodes(INITIAL_STAR_MAP_NODES, {
      ...defaultFilter,
      agentScope: 'global',
    });
    expect(globalNodes.every((n) => n.scope === 'global')).toBe(true);

    const agentNodes = filterStarMapNodes(INITIAL_STAR_MAP_NODES, {
      ...defaultFilter,
      agentScope: 'agent-specific',
    });
    expect(agentNodes.every((n) => n.scope === 'agent-specific')).toBe(true);
  });

  it('filters nodes by time window (7d, 30d)', () => {
    const now = Date.now();
    const dayMs = 24 * 3600 * 1000;

    const sevenDaysNodes = filterStarMapNodes(
      INITIAL_STAR_MAP_NODES,
      {
        ...defaultFilter,
        timeSpan: '7d',
      },
      now
    );

    expect(sevenDaysNodes.every((n) => now - n.createdAt <= 7 * dayMs)).toBe(true);
  });

  it('filters links preserving only those with both endpoints visible', () => {
    const firstTwoNodeIds = new Set([
      INITIAL_STAR_MAP_NODES[0].id,
      INITIAL_STAR_MAP_NODES[1].id,
    ]);

    const filteredLinks = filterStarMapLinks(INITIAL_STAR_MAP_LINKS, firstTwoNodeIds);

    for (const link of filteredLinks) {
      expect(firstTwoNodeIds.has(link.sourceId)).toBe(true);
      expect(firstTwoNodeIds.has(link.targetId)).toBe(true);
    }
  });
});
