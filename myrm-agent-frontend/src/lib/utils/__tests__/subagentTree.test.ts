import { describe, it, expect } from 'vitest';
import type { SubagentNode } from '@/store/chat/useSubagentStore';
import {
  buildTree,
  aggregate,
  treeTotals,
  sortNodes,
  filterNodes,
  flattenTree,
  fmtCost,
  fmtTokens,
  fmtBudgetCost,
  extractCostUsd,
  extractTotalTokens,
  extractBudgetTokens,
  extractMaxCostUsd,
  type TreeNode,
} from '../subagentTree';

function mkNode(overrides: Partial<SubagentNode> & { task_id: string }): SubagentNode {
  return {
    parent_task_id: '',
    agent_type: 'general',
    description: `task-${overrides.task_id}`,
    status: 'completed',
    progress: 100,
    ...overrides,
  };
}

function mkRecord(...nodes: SubagentNode[]): Record<string, SubagentNode> {
  const r: Record<string, SubagentNode> = {};
  for (const n of nodes) r[n.task_id] = n;
  return r;
}

// ── extract* helpers ─────────────────────────────────────────────────

describe('extractCostUsd', () => {
  it('reads from token_usage.total_cost_usd', () => {
    expect(extractCostUsd({ ...mkNode({ task_id: 'a' }), token_usage: { total_cost_usd: 1.25 } })).toBeCloseTo(1.25);
  });

  it('parses string cost', () => {
    expect(extractCostUsd({ ...mkNode({ task_id: 'a' }), token_usage: { total_cost_usd: '0.75' } })).toBeCloseTo(0.75);
  });

  it('returns 0 for missing/invalid cost', () => {
    expect(extractCostUsd(mkNode({ task_id: 'a' }))).toBe(0);
    expect(extractCostUsd({ ...mkNode({ task_id: 'a' }), token_usage: { total_cost_usd: 'abc' } })).toBe(0);
    expect(extractCostUsd({ ...mkNode({ task_id: 'a' }), token_usage: { total_cost_usd: Infinity } })).toBe(0);
  });
});

describe('extractTotalTokens', () => {
  it('reads positive total_tokens', () => {
    expect(extractTotalTokens({ ...mkNode({ task_id: 'a' }), token_usage: { total_tokens: 1234 } })).toBe(1234);
  });

  it('returns 0 for zero/missing/negative', () => {
    expect(extractTotalTokens({ ...mkNode({ task_id: 'a' }), token_usage: { total_tokens: 0 } })).toBe(0);
    expect(extractTotalTokens({ ...mkNode({ task_id: 'a' }), token_usage: { total_tokens: -5 } })).toBe(0);
    expect(extractTotalTokens(mkNode({ task_id: 'a' }))).toBe(0);
  });

  it('parses string token count', () => {
    expect(extractTotalTokens({ ...mkNode({ task_id: 'a' }), token_usage: { total_tokens: '4321' } })).toBe(4321);
    expect(extractTotalTokens({ ...mkNode({ task_id: 'a' }), token_usage: { total_tokens: 'abc' } })).toBe(0);
  });
});

describe('extractBudgetTokens / extractMaxCostUsd', () => {
  it('reads budget ceilings from budget payload', () => {
    const node: SubagentNode = {
      ...mkNode({ task_id: 'a' }),
      budget: { budget_tokens: 50_000, max_cost_usd: 2.5 },
    };
    expect(extractBudgetTokens(node)).toBe(50_000);
    expect(extractMaxCostUsd(node)).toBeCloseTo(2.5);
  });

  it('returns 0 when budget is absent or non-finite', () => {
    expect(extractBudgetTokens(mkNode({ task_id: 'a' }))).toBe(0);
    expect(extractMaxCostUsd(mkNode({ task_id: 'a' }))).toBe(0);
    expect(extractBudgetTokens({ ...mkNode({ task_id: 'a' }), budget: { budget_tokens: 'abc' } })).toBe(0);
    expect(extractMaxCostUsd({ ...mkNode({ task_id: 'a' }), budget: { max_cost_usd: Infinity } })).toBe(0);
  });
});

// ── buildTree ────────────────────────────────────────────────────────

describe('buildTree', () => {
  it('returns empty array for empty input', () => {
    expect(buildTree({})).toEqual([]);
  });

  it('creates flat roots when no parent links', () => {
    const roots = buildTree(
      mkRecord(mkNode({ task_id: 'a' }), mkNode({ task_id: 'b' })),
    );
    expect(roots).toHaveLength(2);
    expect(roots.every((r) => r.children.length === 0)).toBe(true);
  });

  it('links children to parents', () => {
    const roots = buildTree(
      mkRecord(
        mkNode({ task_id: 'root' }),
        mkNode({ task_id: 'child1', parent_task_id: 'root' }),
        mkNode({ task_id: 'child2', parent_task_id: 'root' }),
      ),
    );
    expect(roots).toHaveLength(1);
    expect(roots[0].task_id).toBe('root');
    expect(roots[0].children).toHaveLength(2);
  });

  it('orphaned nodes become roots', () => {
    const roots = buildTree(
      mkRecord(
        mkNode({ task_id: 'a', parent_task_id: 'missing' }),
      ),
    );
    expect(roots).toHaveLength(1);
    expect(roots[0].task_id).toBe('a');
  });

  it('builds multi-level tree', () => {
    const roots = buildTree(
      mkRecord(
        mkNode({ task_id: 'root' }),
        mkNode({ task_id: 'mid', parent_task_id: 'root' }),
        mkNode({ task_id: 'leaf', parent_task_id: 'mid' }),
      ),
    );
    expect(roots).toHaveLength(1);
    expect(roots[0].children[0].children[0].task_id).toBe('leaf');
  });
});

// ── aggregate ─────────────────────────────────────────────────────────

describe('aggregate', () => {
  it('leaf node has zero descendants', () => {
    const leaf: TreeNode = {
      ...mkNode({ task_id: 'a', duration_seconds: 5 }),
      children: [],
      token_usage: { total_tokens: 1000, total_cost_usd: 0.5 },
    };
    const agg = aggregate(leaf);
    expect(agg.descendantCount).toBe(0);
    expect(agg.totalCostUsd).toBeCloseTo(0.5);
    expect(agg.totalTokens).toBe(1000);
    expect(agg.totalDurationSeconds).toBe(5);
  });

  it('recursively sums children', () => {
    const child: TreeNode = {
      ...mkNode({ task_id: 'c', duration_seconds: 3, status: 'running' }),
      children: [],
      token_usage: { total_tokens: 500, total_cost_usd: 0.2 },
    };
    const parent: TreeNode = {
      ...mkNode({ task_id: 'p', duration_seconds: 10 }),
      children: [child],
      token_usage: { total_tokens: 2000, total_cost_usd: 1.0 },
    };
    const agg = aggregate(parent);
    expect(agg.descendantCount).toBe(1);
    expect(agg.totalCostUsd).toBeCloseTo(1.2);
    expect(agg.totalTokens).toBe(2500);
    expect(agg.totalDurationSeconds).toBe(13);
    expect(agg.activeCount).toBe(1);
  });

  it('handles string cost gracefully', () => {
    const node: TreeNode = {
      ...mkNode({ task_id: 'x' }),
      children: [],
      token_usage: { total_cost_usd: '0.75' },
    };
    const agg = aggregate(node);
    expect(agg.totalCostUsd).toBeCloseTo(0.75);
  });

  it('ignores legacy budget.cost_usd (never produced by harness)', () => {
    const node: TreeNode = {
      ...mkNode({ task_id: 'y' }),
      children: [],
      budget: { cost_usd: 9.99 },
      token_usage: { total_cost_usd: 0.3 },
    };
    const agg = aggregate(node);
    expect(agg.totalCostUsd).toBeCloseTo(0.3);
  });

  it('handles missing budget/token_usage', () => {
    const node: TreeNode = { ...mkNode({ task_id: 'x' }), children: [] };
    const agg = aggregate(node);
    expect(agg.totalCostUsd).toBe(0);
    expect(agg.totalTokens).toBe(0);
  });
});

// ── treeTotals ────────────────────────────────────────────────────────

describe('treeTotals', () => {
  it('counts agents, failures, active', () => {
    const roots = buildTree(
      mkRecord(
        mkNode({ task_id: 'a', status: 'running', effective_model: 'openai/gpt-4o' }),
        mkNode({ task_id: 'b', status: 'failed', effective_model: 'openai/gpt-4o' }),
        mkNode({ task_id: 'c', status: 'completed', effective_model: 'anthropic/claude-3.5' }),
        mkNode({ task_id: 'd', status: 'timed_out', effective_model: 'anthropic/claude-3.5' }),
      ),
    );
    const t = treeTotals(roots);
    expect(t.totalAgents).toBe(4);
    expect(t.failedCount).toBe(2);
    expect(t.activeCount).toBe(1);
    expect(t.modelMix).toHaveLength(2);
    expect(t.modelMix[0].model).toBe('gpt-4o');
    expect(t.modelMix[0].count).toBe(2);
  });

  it('returns zeros for empty tree', () => {
    const t = treeTotals([]);
    expect(t.totalAgents).toBe(0);
    expect(t.failedCount).toBe(0);
  });
});

// ── sortNodes ─────────────────────────────────────────────────────────

describe('sortNodes', () => {
  const makeNodes = (): TreeNode[] => [
    { ...mkNode({ task_id: 'a', status: 'completed', duration_seconds: 5 }), children: [], token_usage: { total_cost_usd: 0.1 } },
    { ...mkNode({ task_id: 'b', status: 'failed', duration_seconds: 20 }), children: [], token_usage: { total_cost_usd: 2.0 } },
    { ...mkNode({ task_id: 'c', status: 'running', duration_seconds: 10 }), children: [], token_usage: { total_cost_usd: 0.5 } },
  ];

  it('spawn mode preserves order', () => {
    const nodes = makeNodes();
    const sorted = sortNodes(nodes, 'spawn');
    expect(sorted.map((n) => n.task_id)).toEqual(['a', 'b', 'c']);
  });

  it('busiest sorts by cost descending', () => {
    const sorted = sortNodes(makeNodes(), 'busiest');
    expect(sorted[0].task_id).toBe('b');
    expect(sorted[1].task_id).toBe('c');
    expect(sorted[2].task_id).toBe('a');
  });

  it('slowest sorts by duration descending', () => {
    const sorted = sortNodes(makeNodes(), 'slowest');
    expect(sorted[0].task_id).toBe('b');
    expect(sorted[1].task_id).toBe('c');
    expect(sorted[2].task_id).toBe('a');
  });

  it('status sorts failed first, then running, then completed', () => {
    const sorted = sortNodes(makeNodes(), 'status');
    expect(sorted[0].status).toBe('failed');
    expect(sorted[1].status).toBe('running');
    expect(sorted[2].status).toBe('completed');
  });

  it('does not mutate original array', () => {
    const nodes = makeNodes();
    const original = [...nodes];
    sortNodes(nodes, 'busiest');
    expect(nodes.map((n) => n.task_id)).toEqual(original.map((n) => n.task_id));
  });
});

// ── filterNodes ───────────────────────────────────────────────────────

describe('filterNodes', () => {
  const makeTree = (): TreeNode[] => {
    const leaf: TreeNode = {
      ...mkNode({ task_id: 'leaf', status: 'completed', parent_task_id: 'root' }),
      children: [],
    };
    const running: TreeNode = {
      ...mkNode({ task_id: 'run', status: 'running', parent_task_id: 'root' }),
      children: [],
    };
    const root: TreeNode = {
      ...mkNode({ task_id: 'root', status: 'failed' }),
      children: [leaf, running],
    };
    return [root];
  };

  it('all returns same nodes', () => {
    const tree = makeTree();
    expect(filterNodes(tree, 'all')).toBe(tree);
  });

  it('running filters to running/verifying', () => {
    const result = filterNodes(makeTree(), 'running');
    expect(result).toHaveLength(1);
    expect(result[0].task_id).toBe('run');
    expect(result[0].children).toEqual([]);
  });

  it('failed filters to failed/timed_out/interrupted', () => {
    const result = filterNodes(makeTree(), 'failed');
    expect(result).toHaveLength(1);
    expect(result[0].task_id).toBe('root');
    expect(result[0].children).toEqual([]);
  });

  it('leaf filters to nodes without children', () => {
    const result = filterNodes(makeTree(), 'leaf');
    expect(result).toHaveLength(2);
    expect(result.map((n) => n.task_id).sort()).toEqual(['leaf', 'run']);
    result.forEach((n) => expect(n.children).toEqual([]));
  });
});

// ── flattenTree ──────────────────────────────────────────────────────

describe('flattenTree', () => {
  it('flattens nested tree', () => {
    const child: TreeNode = { ...mkNode({ task_id: 'c' }), children: [] };
    const root: TreeNode = { ...mkNode({ task_id: 'r' }), children: [child] };
    const flat = flattenTree([root]);
    expect(flat).toHaveLength(2);
    expect(flat[0].task_id).toBe('r');
    expect(flat[1].task_id).toBe('c');
  });
});

// ── fmtBudgetCost ────────────────────────────────────────────────────

describe('fmtBudgetCost', () => {
  it('formats used/limit with 3+2 decimals', () => {
    expect(fmtBudgetCost(0.5, 2.5)).toBe('$0.500/2.50');
  });

  it('omits limit when not set', () => {
    expect(fmtBudgetCost(0.5, 0)).toBe('$0.500');
  });

  it('keeps tiny amounts readable instead of $0.000', () => {
    expect(fmtBudgetCost(0.0004, 2.5)).toBe('<$0.001/2.50');
    expect(fmtBudgetCost(0.0004, 0)).toBe('<$0.001');
  });
});

// ── fmtCost ──────────────────────────────────────────────────────────

describe('fmtCost', () => {
  it('returns empty for zero or negative', () => {
    expect(fmtCost(0)).toBe('');
    expect(fmtCost(-1)).toBe('');
  });
  it('returns <$0.01 for tiny amounts', () => {
    expect(fmtCost(0.005)).toBe('<$0.01');
  });
  it('formats small amounts with 2 decimals', () => {
    expect(fmtCost(1.234)).toBe('$1.23');
  });
  it('formats large amounts with 1 decimal', () => {
    expect(fmtCost(15.67)).toBe('$15.7');
  });
  it('handles NaN/Infinity', () => {
    expect(fmtCost(NaN)).toBe('');
    expect(fmtCost(Infinity)).toBe('');
  });
});

// ── fmtTokens ────────────────────────────────────────────────────────

describe('fmtTokens', () => {
  it('returns 0 for zero or negative', () => {
    expect(fmtTokens(0)).toBe('0');
    expect(fmtTokens(-10)).toBe('0');
  });
  it('formats small numbers as-is', () => {
    expect(fmtTokens(500)).toBe('500');
  });
  it('formats thousands with k', () => {
    expect(fmtTokens(5432)).toBe('5.4k');
  });
  it('formats large numbers as rounded k', () => {
    expect(fmtTokens(123456)).toBe('123k');
  });
});
