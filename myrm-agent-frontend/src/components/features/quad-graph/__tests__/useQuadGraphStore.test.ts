import { describe, it, expect, beforeEach } from 'vitest';
import { useQuadGraphStore } from '../useQuadGraphStore';

describe('useQuadGraphStore', () => {
  beforeEach(() => {
    useQuadGraphStore.getState().resetToDemoModel();
    useQuadGraphStore.getState().selectNode(null);
    useQuadGraphStore.getState().setActiveLayer('task');
  });

  it('initializes with default demo nodes and edges', () => {
    const state = useQuadGraphStore.getState();
    expect(state.activeLayer).toBe('task');
    expect(state.nodes.length).toBeGreaterThan(0);
    expect(state.edges.length).toBeGreaterThan(0);
    expect(state.selectedNodeId).toBeNull();
    expect(state.isInspectionOpen).toBe(false);
  });

  it('switches activeLayer correctly', () => {
    useQuadGraphStore.getState().setActiveLayer('workflow');
    expect(useQuadGraphStore.getState().activeLayer).toBe('workflow');

    useQuadGraphStore.getState().setActiveLayer('team');
    expect(useQuadGraphStore.getState().activeLayer).toBe('team');

    useQuadGraphStore.getState().setActiveLayer('communication');
    expect(useQuadGraphStore.getState().activeLayer).toBe('communication');
  });

  it('selects and deselects node with inspection open status', () => {
    useQuadGraphStore.getState().selectNode('task_2');
    expect(useQuadGraphStore.getState().selectedNodeId).toBe('task_2');
    expect(useQuadGraphStore.getState().isInspectionOpen).toBe(true);

    useQuadGraphStore.getState().selectNode(null);
    expect(useQuadGraphStore.getState().selectedNodeId).toBeNull();
    expect(useQuadGraphStore.getState().isInspectionOpen).toBe(false);
  });

  it('updates inspection open flag', () => {
    useQuadGraphStore.getState().selectNode('task_1');
    expect(useQuadGraphStore.getState().isInspectionOpen).toBe(true);

    useQuadGraphStore.getState().setInspectionOpen(false);
    expect(useQuadGraphStore.getState().isInspectionOpen).toBe(false);
    expect(useQuadGraphStore.getState().selectedNodeId).toBeNull();
  });

  it('updates hovered node id', () => {
    useQuadGraphStore.getState().setHoveredNodeId('task_3');
    expect(useQuadGraphStore.getState().hoveredNodeId).toBe('task_3');

    useQuadGraphStore.getState().setHoveredNodeId(null);
    expect(useQuadGraphStore.getState().hoveredNodeId).toBeNull();
  });

  it('updates node status and output snapshot', () => {
    useQuadGraphStore.getState().updateNodeStatus('task_3', 'completed', 'Output generated OK');
    const node = useQuadGraphStore.getState().nodes.find((n) => n.id === 'task_3');
    expect(node?.status).toBe('completed');
    expect(node?.outputSnapshot).toBe('Output generated OK');
  });

  it('handles steerNode payload actions', () => {
    useQuadGraphStore.getState().steerNode({
      nodeId: 'task_3',
      instruction: 'pause immediately',
      action: 'pause',
    });
    let node = useQuadGraphStore.getState().nodes.find((n) => n.id === 'task_3');
    expect(node?.status).toBe('pending');

    useQuadGraphStore.getState().steerNode({
      nodeId: 'task_3',
      instruction: 'resume run',
      action: 'resume',
    });
    node = useQuadGraphStore.getState().nodes.find((n) => n.id === 'task_3');
    expect(node?.status).toBe('running');

    useQuadGraphStore.getState().steerNode({
      nodeId: 'task_3',
      instruction: 'retry from scratch',
      action: 'retry',
    });
    node = useQuadGraphStore.getState().nodes.find((n) => n.id === 'task_3');
    expect(node?.status).toBe('running');
  });

  it('calculates summary statistics correctly', () => {
    const summary = useQuadGraphStore.getState().getSummary();
    expect(summary.totalNodes).toBe(useQuadGraphStore.getState().nodes.length);
    expect(summary.totalEdges).toBe(useQuadGraphStore.getState().edges.length);
    expect(summary.completedNodes).toBeGreaterThan(0);
    expect(summary.runningNodes).toBeGreaterThan(0);
  });
});
