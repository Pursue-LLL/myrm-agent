import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NodeInspectionDrawer } from '../NodeInspectionDrawer';
import type { GraphNode } from '../quadGraphTypes';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('NodeInspectionDrawer', () => {
  const dummyNode: GraphNode = {
    id: 'test_node_1',
    label: 'SQL 注入过滤与语法树解析',
    layer: 'workflow',
    status: 'running',
    role: 'AST Parser',
    durationMs: 450,
    dependencies: ['dep_1', 'dep_2'],
    inputSnapshot: '{"query": "SELECT * FROM users"}',
    outputSnapshot: '{"ast": "ok"}',
  };

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <NodeInspectionDrawer
        node={dummyNode}
        isOpen={false}
        onClose={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer content when open with node details', () => {
    render(
      <NodeInspectionDrawer
        node={dummyNode}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByTestId('node-inspection-drawer-root')).toBeInTheDocument();
    expect(screen.getByTestId('node-inspection-drawer')).toBeInTheDocument();
    expect(screen.getByText('SQL 注入过滤与语法树解析')).toBeInTheDocument();
    expect(screen.getByText('ID: test_node_1')).toBeInTheDocument();
    expect(screen.getByText('AST Parser')).toBeInTheDocument();
    expect(screen.getByTestId('node-input-snapshot')).toHaveTextContent('{"query": "SELECT * FROM users"}');
    expect(screen.getByTestId('node-output-snapshot')).toHaveTextContent('{"ast": "ok"}');
  });

  it('calls onClose when close button is clicked', () => {
    const onCloseMock = vi.fn();
    render(
      <NodeInspectionDrawer
        node={dummyNode}
        isOpen={true}
        onClose={onCloseMock}
      />
    );

    fireEvent.click(screen.getByTestId('close-inspection-btn'));
    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });

  it('triggers pause and retry actions', () => {
    const onSteerMock = vi.fn();
    render(
      <NodeInspectionDrawer
        node={dummyNode}
        isOpen={true}
        onClose={vi.fn()}
        onSteerNode={onSteerMock}
      />
    );

    // Node is running -> shows pause button
    fireEvent.click(screen.getByTestId('pause-node-btn'));
    expect(onSteerMock).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeId: 'test_node_1',
        action: 'pause',
      })
    );

    // Retry button
    fireEvent.click(screen.getByTestId('retry-node-btn'));
    expect(onSteerMock).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeId: 'test_node_1',
        action: 'retry',
      })
    );
  });

  it('submits steer instruction on button click and enter key', () => {
    const onSteerMock = vi.fn();
    render(
      <NodeInspectionDrawer
        node={dummyNode}
        isOpen={true}
        onClose={vi.fn()}
        onSteerNode={onSteerMock}
      />
    );

    const input = screen.getByTestId('steer-input');
    const submitBtn = screen.getByTestId('submit-steer-btn');

    // Button disabled when empty
    expect(submitBtn).toBeDisabled();

    // Type text
    fireEvent.change(input, { target: { value: 'Switch to strict AST parser mode' } });
    expect(submitBtn).not.toBeDisabled();

    fireEvent.click(submitBtn);
    expect(onSteerMock).toHaveBeenCalledWith({
      nodeId: 'test_node_1',
      instruction: 'Switch to strict AST parser mode',
      action: 'steer',
    });

    // Enter key submit
    fireEvent.change(input, { target: { value: 'Skip AST validation on test table' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    expect(onSteerMock).toHaveBeenCalledWith({
      nodeId: 'test_node_1',
      instruction: 'Skip AST validation on test table',
      action: 'steer',
    });
  });
});
