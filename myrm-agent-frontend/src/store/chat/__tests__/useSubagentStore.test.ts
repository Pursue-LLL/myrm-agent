import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSubagentStore, isNodeOvertime, type SubagentNode } from '../useSubagentStore';

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(),
}));

import { fetchWithTimeout } from '@/lib/api';
const mockFetchWithTimeout = vi.mocked(fetchWithTimeout);

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

describe('internal nodes', () => {
  it('setNodes skips internal nodes', () => {
    useSubagentStore
      .getState()
      .setNodes([
        makeNode({ task_id: 'biz', internal: false }),
        makeNode({ task_id: 'verify-worker-1', internal: true }),
      ]);
    const nodes = useSubagentStore.getState().nodes;
    expect(nodes['biz']).toBeDefined();
    expect(nodes['verify-worker-1']).toBeUndefined();
  });
});

describe('setNodes terminal-state protection', () => {
  beforeEach(() => {
    useSubagentStore.getState().clear();
  });

  it('does not downgrade a cancelled node to running via late SSE snapshot', () => {
    useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status: 'cancelled' })]);
    useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status: 'running', progress: 40 })]);
    const node = useSubagentStore.getState().nodes['t1'];
    expect(node.status).toBe('cancelled');
  });

  it('keeps terminal status for completed/failed/timed_out when running arrives', () => {
    for (const status of ['completed', 'failed', 'timed_out'] as const) {
      useSubagentStore.getState().clear();
      useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status })]);
      useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status: 'running' })]);
      expect(useSubagentStore.getState().nodes['t1'].status).toBe(status);
    }
  });

  it('allows running -> completed forward transition', () => {
    useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status: 'running' })]);
    useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status: 'completed', progress: 100 })]);
    expect(useSubagentStore.getState().nodes['t1'].status).toBe('completed');
  });

  it('still merges non-status fields from late snapshots', () => {
    useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status: 'cancelled' })]);
    useSubagentStore.getState().setNodes([makeNode({ task_id: 't1', status: 'running', last_tool: 'bash' })]);
    const node = useSubagentStore.getState().nodes['t1'];
    expect(node.status).toBe('cancelled');
    expect(node.last_tool).toBe('bash');
  });
});

describe('fetchSubagents', () => {
  beforeEach(() => {
    useSubagentStore.getState().clear();
    mockFetchWithTimeout.mockReset();
  });

  it('hydrates store nodes from the subagents API', async () => {
    const nodes = [makeNode({ task_id: 't-api', status: 'completed', progress: 100 })];
    mockFetchWithTimeout.mockResolvedValue({
      json: vi.fn().mockResolvedValue({ data: nodes }),
    } as unknown as Response);

    await useSubagentStore.getState().fetchSubagents('chat-1');

    expect(mockFetchWithTimeout).toHaveBeenCalledWith('/chats/chat-1/subagents');
    expect(useSubagentStore.getState().nodes['t-api']).toBeDefined();
    expect(useSubagentStore.getState().nodes['t-api'].status).toBe('completed');
  });

  it('ignores non-array data payloads', async () => {
    mockFetchWithTimeout.mockResolvedValue({
      json: vi.fn().mockResolvedValue({ data: {} }),
    } as unknown as Response);

    await useSubagentStore.getState().fetchSubagents('chat-2');

    expect(Object.keys(useSubagentStore.getState().nodes)).toHaveLength(0);
  });

  it('does nothing without a chat id', async () => {
    await useSubagentStore.getState().fetchSubagents('');

    expect(mockFetchWithTimeout).not.toHaveBeenCalled();
  });

  it('survives API failure without throwing', async () => {
    mockFetchWithTimeout.mockRejectedValue(new Error('network down'));

    await expect(useSubagentStore.getState().fetchSubagents('chat-3')).resolves.toBeUndefined();
  });
});
