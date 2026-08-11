import { describe, it, expect } from 'vitest';
import type { FissionTopology, SubagentNode } from '@/store/chat/useSubagentStore';
import {
  buildTopologyModel,
  buildFissionTopologyModel,
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

  it('truncates long description labels', () => {
    const m = buildTopologyModel([mkNode({ task_id: 'a', description: 'y'.repeat(120) })]);
    expect(m.nodes[0].label.length).toBeLessThanOrEqual(60);
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

  it('counts running fission nodes as active', () => {
    const m = buildFissionTopologyModel(topology);
    expect(m.activeCount).toBe(1);
  });

  it('aggregates fission costs', () => {
    const m = buildFissionTopologyModel(topology);
    expect(m.totalCostUsd).toBeCloseTo(0.5);
  });
});
