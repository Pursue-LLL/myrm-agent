import { describe, it, expect } from 'vitest';
import type { FissionTopology, SubagentNode } from '@/store/chat/useSubagentStore';
import {
  buildTopologyModel,
  buildFissionTopologyModel,
  buildMergedTopologyModel,
  toneForStatus,
  truncateLabel,
} from '../taskTopologyModel';

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

// ── toneForStatus ────────────────────────────────────────────────────

describe('toneForStatus', () => {
  it('maps running/verifying to active', () => {
    expect(toneForStatus('running')).toBe('active');
    expect(toneForStatus('verifying')).toBe('active');
  });

  it('maps terminal failure statuses to danger', () => {
    expect(toneForStatus('failed')).toBe('danger');
    expect(toneForStatus('timed_out')).toBe('danger');
    expect(toneForStatus('interrupted')).toBe('danger');
    expect(toneForStatus('cancelled')).toBe('danger');
    expect(toneForStatus('cancelled_by_budget')).toBe('danger');
  });

  it('maps completed to success', () => {
    expect(toneForStatus('completed')).toBe('success');
  });

  it('falls back to muted for unknown statuses', () => {
    expect(toneForStatus('whatever')).toBe('muted');
  });
});

// ── truncateLabel ────────────────────────────────────────────────────

describe('truncateLabel', () => {
  it('keeps short text untouched', () => {
    expect(truncateLabel('short')).toBe('short');
  });

  it('truncates long text with ellipsis', () => {
    const long = 'x'.repeat(100);
    expect(truncateLabel(long)).toHaveLength(60);
    expect(truncateLabel(long)).toMatch(/…$/);
  });
});

// ── buildTopologyModel ───────────────────────────────────────────────

describe('buildTopologyModel', () => {
  it('returns an empty model for no nodes', () => {
    const m = buildTopologyModel([]);
    expect(m.nodes).toHaveLength(0);
    expect(m.edges).toHaveLength(0);
    expect(m.activeCount).toBe(0);
  });

  it('builds a parent-child tree graph', () => {
    const m = buildTopologyModel([
      mkNode({ task_id: 'root', status: 'running', progress: 40 }),
      mkNode({ task_id: 'child', parent_task_id: 'root', status: 'completed' }),
    ]);
    expect(m.nodes).toHaveLength(2);
    expect(m.edges).toEqual([{ source: 'root', target: 'child' }]);
    expect(m.activeCount).toBe(1);
  });

  it('drops dangling edges whose parent is missing', () => {
    const m = buildTopologyModel([mkNode({ task_id: 'orphan', parent_task_id: 'ghost' })]);
    expect(m.edges).toHaveLength(0);
    expect(m.nodes).toHaveLength(1);
  });

  it('aggregates cost/tokens/duration across all nodes', () => {
    const m = buildTopologyModel([
      { ...mkNode({ task_id: 'a', duration_seconds: 10 }), token_usage: { total_cost_usd: 1, total_tokens: 100 } },
      { ...mkNode({ task_id: 'b', duration_seconds: 20 }), token_usage: { total_cost_usd: 2, total_tokens: 200 } },
    ]);
    expect(m.totalCostUsd).toBeCloseTo(3);
    expect(m.totalTokens).toBe(300);
    expect(m.totalDurationSeconds).toBe(30);
  });

  it('counts failed nodes as danger', () => {
    const m = buildTopologyModel([
      mkNode({ task_id: 'f', status: 'failed', error: 'boom' }),
      mkNode({ task_id: 'c', status: 'completed' }),
    ]);
    expect(m.failedCount).toBe(1);
    expect(m.nodes.find((n) => n.taskId === 'f')?.tone).toBe('danger');
    expect(m.nodes.find((n) => n.taskId === 'f')?.error).toBe('boom');
  });

  it('downgrades completed nodes with failed verification to danger', () => {
    const m = buildTopologyModel([
      mkNode({
        task_id: 'v',
        status: 'completed',
        verification: { passed: false, rounds: 2, max_rounds: 2, confidence: 'LOW' },
      }),
      mkNode({
        task_id: 'p',
        status: 'completed',
        verification: { passed: true, rounds: 1, max_rounds: 2, confidence: 'HIGH' },
      }),
    ]);
    expect(m.failedCount).toBe(1);
    expect(m.nodes.find((n) => n.taskId === 'v')?.tone).toBe('danger');
    expect(m.nodes.find((n) => n.taskId === 'v')?.verification?.passed).toBe(false);
    expect(m.nodes.find((n) => n.taskId === 'p')?.tone).toBe('success');
    expect(m.nodes.find((n) => n.taskId === 'p')?.verification?.passed).toBe(true);
  });

  it('truncates long description labels', () => {
    const m = buildTopologyModel([mkNode({ task_id: 'a', description: 'y'.repeat(120) })]);
    expect(m.nodes[0].label.length).toBeLessThanOrEqual(60);
  });

  it('excludes internal nodes and their edges', () => {
    const m = buildTopologyModel([
      mkNode({ task_id: 'root', status: 'completed' }),
      mkNode({ task_id: 'biz', parent_task_id: 'root', status: 'completed' }),
      mkNode({ task_id: 'verify-worker-1', parent_task_id: 'root', status: 'completed', internal: true }),
    ]);
    const ids = m.nodes.map((n) => n.taskId);
    expect(ids).toEqual(['root', 'biz']);
    expect(m.edges.some((e) => e.target === 'verify-worker-1')).toBe(false);
  });
});

// ── buildFissionTopologyModel ────────────────────────────────────────

describe('buildFissionTopologyModel', () => {
  const topology: FissionTopology = {
    fission_id: 'fission-12345678',
    nodes: [
      { node_id: 'n1', agent_type: 'researcher', objective: 'research market', status: 'completed', cost_usd: 0.5 },
      { node_id: 'n2', agent_type: 'writer', objective: 'write report', status: 'running', error: null },
    ],
    total_cost_usd: 0.5,
  };

  it('returns an empty model for null topology', () => {
    const m = buildFissionTopologyModel(null);
    expect(m.nodes).toHaveLength(0);
    expect(m.edges).toHaveLength(0);
  });

  it('creates a root node plus one edge per fission node', () => {
    const m = buildFissionTopologyModel(topology);
    expect(m.nodes).toHaveLength(3);
    expect(m.edges).toHaveLength(2);
    expect(m.nodes[0].isRoot).toBe(true);
    expect(m.edges[0].source).toBe(m.nodes[0].taskId);
  });

  it('marks the root active while any fission node is running', () => {
    const m = buildFissionTopologyModel(topology);
    expect(m.nodes[0].status).toBe('running');
    expect(m.nodes[0].tone).toBe('active');
  });

  it('marks the root completed when every fission node has finished', () => {
    const done: FissionTopology = {
      fission_id: 'fission-12345678',
      nodes: [
        { node_id: 'n1', agent_type: 'researcher', objective: 'research', status: 'completed' },
        { node_id: 'n2', agent_type: 'writer', objective: 'write', status: 'failed', error: 'boom' },
      ],
      total_cost_usd: 0,
    };
    const m = buildFissionTopologyModel(done);
    expect(m.nodes[0].status).toBe('completed');
    expect(m.nodes[0].tone).toBe('success');
    expect(m.failedCount).toBe(1);
  });

  it('counts running fission nodes as active', () => {
    const m = buildFissionTopologyModel(topology);
    expect(m.activeCount).toBe(1);
  });

  it('aggregates fission costs', () => {
    const m = buildFissionTopologyModel(topology);
    expect(m.totalCostUsd).toBeCloseTo(0.5);
  });

  it('keys the fission root by fission id so it never collides with subagent task ids', () => {
    const m = buildFissionTopologyModel(topology);
    expect(m.nodes[0].taskId).toBe(`fission-${topology.fission_id}`);
    expect(m.nodes[0].taskId).not.toBe('fission-root');
  });
});

// ── buildMergedTopologyModel ──────────────────────────────────────────

describe('buildMergedTopologyModel', () => {
  const topology: FissionTopology = {
    fission_id: 'fission-12345678',
    nodes: [{ node_id: 'n1', agent_type: 'researcher', objective: 'research', status: 'running', cost_usd: 0.5 }],
    total_cost_usd: 0.5,
  };

  it('falls back to the subagent tree when no fission topology exists', () => {
    const m = buildMergedTopologyModel([mkNode({ task_id: 'root', status: 'running' })], null);
    expect(m.nodes).toHaveLength(1);
    expect(m.edges).toHaveLength(0);
    expect(m.nodes[0].isRoot).toBeFalsy();
  });

  it('merges tree and fission nodes into one graph with unique ids', () => {
    const m = buildMergedTopologyModel([mkNode({ task_id: 'root', status: 'running' })], topology);
    expect(m.nodes).toHaveLength(3);
    expect(m.edges).toHaveLength(1);
    const ids = new Set(m.nodes.map((n) => n.taskId));
    expect(ids.size).toBe(3);
    expect(m.nodes.find((n) => n.isRoot)?.taskId).toBe(`fission-${topology.fission_id}`);
  });

  it('accumulates summary metrics from both sources', () => {
    const m = buildMergedTopologyModel(
      [{ ...mkNode({ task_id: 'root', status: 'completed' }), token_usage: { total_cost_usd: 1, total_tokens: 100 } }],
      {
        ...topology,
        nodes: [{ node_id: 'n1', agent_type: 'researcher', objective: 'research', status: 'completed', cost_usd: 0.5 }],
      },
    );
    expect(m.activeCount).toBe(0);
    expect(m.totalCostUsd).toBeCloseTo(1.5);
    expect(m.totalTokens).toBe(100);
    expect(m.totalDurationSeconds).toBe(0);
  });

  it('namespaces fission children so ids never collide with subagent task ids', () => {
    const subagent = [
      mkNode({ task_id: 'n1', status: 'completed' }),
      mkNode({ task_id: 'root', status: 'completed', parent_task_id: 'n1' }),
    ];
    const m = buildMergedTopologyModel(subagent, topology);
    const ids = m.nodes.map((n) => n.taskId);
    expect(new Set(ids).size).toBe(ids.length);
    expect(m.edges).toHaveLength(2);
    expect(m.nodes.filter((n) => n.taskId === 'n1')).toHaveLength(1);
    expect(m.nodes.filter((n) => n.taskId.startsWith('fission-'))).toHaveLength(2);
  });

  it('counts active nodes from both sources', () => {
    const m = buildMergedTopologyModel([mkNode({ task_id: 'root', status: 'completed' })], topology);
    expect(m.activeCount).toBe(1);
    expect(m.failedCount).toBe(0);
  });
});
