import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GraphViewportSwitcher } from '../GraphViewportSwitcher';
import type { GraphLayerType } from '../quadGraphTypes';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('GraphViewportSwitcher', () => {
  const nodeCounts: Record<GraphLayerType, number> = {
    task: 5,
    workflow: 4,
    team: 4,
    communication: 3,
  };

  it('renders all four layer tabs with count badges', () => {
    render(
      <GraphViewportSwitcher
        activeLayer="task"
        onSelectLayer={vi.fn()}
        nodeCountsByLayer={nodeCounts}
      />
    );

    expect(screen.getByTestId('graph-viewport-switcher-root')).toBeInTheDocument();
    expect(screen.getByTestId('viewport-layer-btn-task')).toBeInTheDocument();
    expect(screen.getByTestId('viewport-layer-btn-workflow')).toBeInTheDocument();
    expect(screen.getByTestId('viewport-layer-btn-team')).toBeInTheDocument();
    expect(screen.getByTestId('viewport-layer-btn-communication')).toBeInTheDocument();

    expect(screen.getByTestId('layer-count-task')).toHaveTextContent('5');
    expect(screen.getByTestId('layer-count-workflow')).toHaveTextContent('4');
    expect(screen.getByTestId('layer-count-team')).toHaveTextContent('4');
    expect(screen.getByTestId('layer-count-communication')).toHaveTextContent('3');
  });

  it('calls onSelectLayer when clicking tab buttons', () => {
    const onSelectLayerMock = vi.fn();
    render(
      <GraphViewportSwitcher
        activeLayer="task"
        onSelectLayer={onSelectLayerMock}
        nodeCountsByLayer={nodeCounts}
      />
    );

    fireEvent.click(screen.getByTestId('viewport-layer-btn-workflow'));
    expect(onSelectLayerMock).toHaveBeenCalledWith('workflow');

    fireEvent.click(screen.getByTestId('viewport-layer-btn-team'));
    expect(onSelectLayerMock).toHaveBeenCalledWith('team');

    fireEvent.click(screen.getByTestId('viewport-layer-btn-communication'));
    expect(onSelectLayerMock).toHaveBeenCalledWith('communication');
  });

  it('renders active style on the selected layer button', () => {
    render(
      <GraphViewportSwitcher
        activeLayer="workflow"
        onSelectLayer={vi.fn()}
        nodeCountsByLayer={nodeCounts}
      />
    );

    const activeBtn = screen.getByTestId('viewport-layer-btn-workflow');
    expect(activeBtn.className).toContain('bg-blue-600');

    const inactiveBtn = screen.getByTestId('viewport-layer-btn-task');
    expect(inactiveBtn.className).toContain('text-slate-400');
  });
});
