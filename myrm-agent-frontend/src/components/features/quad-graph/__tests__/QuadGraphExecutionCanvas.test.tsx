import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QuadGraphExecutionCanvas } from '../QuadGraphExecutionCanvas';
import { useQuadGraphStore } from '../useQuadGraphStore';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('QuadGraphExecutionCanvas', () => {
  beforeEach(() => {
    useQuadGraphStore.getState().resetToDemoModel();
    useQuadGraphStore.getState().selectNode(null);
    useQuadGraphStore.getState().setActiveLayer('task');
  });

  it('renders canvas with top HUD switcher, zoom controls, and demo nodes', () => {
    render(<QuadGraphExecutionCanvas />);

    expect(screen.getByTestId('quad-graph-canvas-root')).toBeInTheDocument();
    expect(screen.getByTestId('graph-viewport-switcher-root')).toBeInTheDocument();
    expect(screen.getByTestId('zoom-in-btn')).toBeInTheDocument();
    expect(screen.getByTestId('zoom-out-btn')).toBeInTheDocument();
    expect(screen.getByTestId('zoom-reset-btn')).toBeInTheDocument();

    // Default layer is 'task', verify demo task node exists
    expect(screen.getByTestId('graph-node-task_1')).toBeInTheDocument();
    expect(screen.getByText('1. 需求意图解析与业务建模')).toBeInTheDocument();
  });

  it('handles zoom in, zoom out, and reset zoom properly', () => {
    render(<QuadGraphExecutionCanvas />);

    const container = screen.getByTestId('graph-transform-container');
    expect(container).toHaveStyle({ transform: 'scale(1)' });

    // Zoom in
    fireEvent.click(screen.getByTestId('zoom-in-btn'));
    expect(container).toHaveStyle({ transform: 'scale(1.15)' });

    // Zoom out
    fireEvent.click(screen.getByTestId('zoom-out-btn'));
    expect(container).toHaveStyle({ transform: 'scale(1)' });

    // Zoom out again
    fireEvent.click(screen.getByTestId('zoom-out-btn'));
    expect(container).toHaveStyle({ transform: 'scale(0.85)' });

    // Reset zoom
    fireEvent.click(screen.getByTestId('zoom-reset-btn'));
    expect(container).toHaveStyle({ transform: 'scale(1)' });
  });

  it('selects a node and opens the inspection drawer upon clicking', () => {
    const onSteerMock = vi.fn();
    render(<QuadGraphExecutionCanvas onSteerNode={onSteerMock} />);

    // Click on node task_1
    const node1 = screen.getByTestId('graph-node-task_1');
    fireEvent.click(node1);

    expect(useQuadGraphStore.getState().selectedNodeId).toBe('task_1');
    const drawer = screen.getByTestId('node-inspection-drawer');
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByText('ID: task_1')).toBeInTheDocument();

    // Close the drawer
    fireEvent.click(screen.getByTestId('close-inspection-btn'));
    expect(screen.queryByTestId('node-inspection-drawer')).toBeNull();
  });

  it('switches viewport layer and displays corresponding nodes', () => {
    render(<QuadGraphExecutionCanvas />);

    // Switch to workflow layer
    fireEvent.click(screen.getByTestId('viewport-layer-btn-workflow'));

    expect(useQuadGraphStore.getState().activeLayer).toBe('workflow');
    expect(screen.getByTestId('graph-node-wf_1')).toBeInTheDocument();
    expect(screen.getByText('Prompt 语义分解')).toBeInTheDocument();
  });

  it('renders empty view when active layer has no nodes', () => {
    const customEmptyModel = {
      layer: 'task' as const,
      nodes: [],
      edges: [],
    };

    render(<QuadGraphExecutionCanvas model={customEmptyModel} />);
    expect(screen.getByTestId('empty-layer-view')).toBeInTheDocument();
  });
});
