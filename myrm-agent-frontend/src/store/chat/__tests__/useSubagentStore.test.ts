import { describe, it, expect, beforeEach } from 'vitest';
import { useSubagentStore, isNodeOvertime, type SubagentNode } from '../useSubagentStore';

function makeNode(overrides: Partial<SubagentNode> = {}): SubagentNode {
  return {
    task_id: 'test-1',
    parent_task_id: 'root',
    agent_type: 'worker',
    description: 'test node',
    status: 'running',
    progress: 10,
    ...overrides,
  };
}

describe('useSubagentStore', () => {
  beforeEach(() => {
    useSubagentStore.getState().clear();
  });

  describe('upsertNode', () => {
    it('creates a new node if not exists', () => {
      useSubagentStore.getState().upsertNode({ task_id: 'abc', status: 'running', description: 'hi' });
      const node = useSubagentStore.getState().nodes['abc'];
      expect(node).toBeDefined();
      expect(node.status).toBe('running');
      expect(node.description).toBe('hi');
    });

    it('merges with existing node', () => {
      useSubagentStore.getState().upsertNode({ task_id: 'abc', status: 'running', description: 'old' });
      useSubagentStore.getState().upsertNode({ task_id: 'abc', description: 'new' });
      expect(useSubagentStore.getState().nodes['abc'].description).toBe('new');
      expect(useSubagentStore.getState().nodes['abc'].status).toBe('running');
    });
  });

  describe('updateEstimate', () => {
    it('calculates estimatedTotalDuration from startedAt + etaSeconds', () => {
      const now = Date.now();
      useSubagentStore.getState().upsertNode({ task_id: 't1', startedAt: now - 5000 });
      useSubagentStore.getState().updateEstimate('t1', 10);
      const node = useSubagentStore.getState().nodes['t1'];
      expect(node.estimatedTotalDuration).toBeGreaterThan(14000);
      expect(node.estimatedTotalDuration).toBeLessThan(16000);
    });

    it('does nothing if node has no startedAt', () => {
      useSubagentStore.getState().upsertNode({ task_id: 't2' });
      useSubagentStore.getState().updateEstimate('t2', 10);
      expect(useSubagentStore.getState().nodes['t2'].estimatedTotalDuration).toBeUndefined();
    });

    it('does nothing for non-existent node', () => {
      useSubagentStore.getState().updateEstimate('ghost', 10);
      expect(useSubagentStore.getState().nodes['ghost']).toBeUndefined();
    });
  });

  describe('dismissOvertime', () => {
    it('sets overtimeDismissed to true', () => {
      useSubagentStore.getState().upsertNode({ task_id: 't1' });
      useSubagentStore.getState().dismissOvertime('t1');
      expect(useSubagentStore.getState().nodes['t1'].overtimeDismissed).toBe(true);
    });

    it('does nothing for non-existent node', () => {
      useSubagentStore.getState().dismissOvertime('ghost');
      expect(useSubagentStore.getState().nodes['ghost']).toBeUndefined();
    });
  });
});

describe('isNodeOvertime', () => {
  it('returns false if status is not running', () => {
    expect(isNodeOvertime(makeNode({ status: 'completed', startedAt: 1 }))).toBe(false);
  });

  it('returns false if no startedAt', () => {
    expect(isNodeOvertime(makeNode({ startedAt: undefined }))).toBe(false);
  });

  it('returns false if overtimeDismissed', () => {
    expect(isNodeOvertime(makeNode({ startedAt: Date.now() - 200_000, overtimeDismissed: true }))).toBe(false);
  });

  it('returns false if elapsed < 60s absolute threshold', () => {
    expect(isNodeOvertime(makeNode({ startedAt: Date.now() - 30_000 }))).toBe(false);
  });

  it('returns true when elapsed > estimatedTotalDuration * 2 and > 60s', () => {
    const node = makeNode({
      startedAt: Date.now() - 150_000,
      estimatedTotalDuration: 60_000,
    });
    expect(isNodeOvertime(node)).toBe(true);
  });

  it('returns false when elapsed < estimatedTotalDuration * 2 even if > 60s', () => {
    const node = makeNode({
      startedAt: Date.now() - 70_000,
      estimatedTotalDuration: 100_000,
    });
    expect(isNodeOvertime(node)).toBe(false);
  });

  it('returns true when no ETA, elapsed > 90s, and progress < 30%', () => {
    const node = makeNode({
      startedAt: Date.now() - 100_000,
      progress: 10,
    });
    expect(isNodeOvertime(node)).toBe(true);
  });

  it('returns false when no ETA, elapsed > 90s, but progress >= 30%', () => {
    const node = makeNode({
      startedAt: Date.now() - 100_000,
      progress: 50,
    });
    expect(isNodeOvertime(node)).toBe(false);
  });

  it('returns false when no ETA, elapsed < 90s, and progress < 30%', () => {
    const node = makeNode({
      startedAt: Date.now() - 70_000,
      progress: 10,
    });
    expect(isNodeOvertime(node)).toBe(false);
  });
});
