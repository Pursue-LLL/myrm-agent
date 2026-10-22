import { describe, it, expect, beforeEach } from 'vitest';
import { useFleetObserverStore } from '../useFleetObserverStore';

describe('useFleetObserverStore', () => {
  beforeEach(() => {
    useFleetObserverStore.getState().resetState();
  });

  it('initializes with default nodes, links, and deliberation metrics', () => {
    const state = useFleetObserverStore.getState();
    expect(state.nodes.length).toBeGreaterThanOrEqual(3);
    expect(state.links.length).toBeGreaterThanOrEqual(2);
    expect(state.metrics.convergenceScore).toBeGreaterThan(0);
    expect(state.executionMode).toBe('running');
  });

  it('pauses and resumes fleet execution correctly', () => {
    const store = useFleetObserverStore.getState();
    store.pauseFleet();

    const pausedState = useFleetObserverStore.getState();
    expect(pausedState.executionMode).toBe('paused');
    expect(pausedState.nodes.some((n) => n.status === 'paused')).toBe(true);

    store.resumeFleet();
    const resumedState = useFleetObserverStore.getState();
    expect(resumedState.executionMode).toBe('running');
    expect(resumedState.nodes.some((n) => n.status === 'busy')).toBe(true);
  });

  it('steps fleet forward advancing link progress and convergence score', () => {
    const store = useFleetObserverStore.getState();
    const initialScore = store.metrics.convergenceScore;
    const initialRounds = store.metrics.activeRounds;

    store.stepFleet();
    const steppedState = useFleetObserverStore.getState();
    expect(steppedState.executionMode).toBe('stepping');
    expect(steppedState.metrics.convergenceScore).toBeGreaterThanOrEqual(initialScore);
    expect(steppedState.metrics.activeRounds).toBe(initialRounds + 1);
  });

  it('selects active fleet node', () => {
    const store = useFleetObserverStore.getState();
    store.selectNode('node-gpu-cluster');
    expect(useFleetObserverStore.getState().selectedNodeId).toBe('node-gpu-cluster');
  });

  it('injects director human intervention command and updates target node', () => {
    const store = useFleetObserverStore.getState();
    const intervention = store.injectDirectorCommand(
      'node-gpu-cluster',
      '强制采用深度反向验证'
    );

    expect(intervention.targetNodeId).toBe('node-gpu-cluster');
    expect(intervention.commandText).toBe('强制采用深度反向验证');

    const state = useFleetObserverStore.getState();
    expect(state.interventions.length).toBe(1);

    const targetNode = state.nodes.find((n) => n.id === 'node-gpu-cluster');
    expect(targetNode?.currentTask).toContain('强制采用深度反向验证');
    expect(targetNode?.status).toBe('busy');
  });

  it('updates specific node status', () => {
    const store = useFleetObserverStore.getState();
    store.updateNodeStatus('node-cloud-sandbox', 'idle');

    const updated = useFleetObserverStore
      .getState()
      .nodes.find((n) => n.id === 'node-cloud-sandbox');
    expect(updated?.status).toBe('idle');
  });
});
