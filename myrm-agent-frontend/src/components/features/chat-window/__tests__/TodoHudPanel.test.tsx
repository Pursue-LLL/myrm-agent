'use client';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  TodoHudPanel,
  TodoItemData,
} from '../TodoHudPanel';

const mockItems: TodoItemData[] = [
  {
    itemId: 'todo-01',
    title: 'Design distributed database schema',
    status: 'completed',
    assignee: 'architect',
  },
  {
    itemId: 'todo-02',
    title: 'Implement gRPC streaming service',
    status: 'in_progress',
    assignee: 'coder',
  },
  {
    itemId: 'todo-03',
    title: 'Run end-to-end stress testing',
    status: 'pending',
    assignee: 'tester',
  },
];

describe('TodoHudPanel', () => {
  it('renders empty state when no items provided', () => {
    render(<TodoHudPanel sessionId="test-sess" items={[]} />);

    expect(screen.getByTestId('empty-todo-state')).toBeInTheDocument();
    expect(screen.getByText('暂无活跃计划声明')).toBeInTheDocument();
    expect(screen.getByText('完成度 0%')).toBeInTheDocument();
    expect(
      screen.getByText('Todo items are plan declarations, not execution evidence.')
    ).toBeInTheDocument();
  });

  it('renders items list with status icons, assignee badges, and metrics', () => {
    render(<TodoHudPanel sessionId="test-sess" items={mockItems} />);

    expect(screen.getByTestId('todo-items-list')).toBeInTheDocument();
    expect(screen.getByText('Design distributed database schema')).toBeInTheDocument();
    expect(screen.getByText('Implement gRPC streaming service')).toBeInTheDocument();
    expect(screen.getByText('Run end-to-end stress testing')).toBeInTheDocument();

    // Check counts in header: 1 completed out of 3 = 33%
    expect(screen.getByText('完成度 33%')).toBeInTheDocument();
    expect(screen.getByText('已完 1')).toBeInTheDocument();
    expect(screen.getByText('进行中 1')).toBeInTheDocument();
    expect(screen.getByText('待办 1')).toBeInTheDocument();

    // Check assignee badges
    expect(screen.getByText('@architect')).toBeInTheDocument();
    expect(screen.getByText('@coder')).toBeInTheDocument();
    expect(screen.getByText('@tester')).toBeInTheDocument();
  });

  it('handles status cycling when clicking status icon', () => {
    const onUpdateStatus = vi.fn();
    render(<TodoHudPanel sessionId="test-sess" items={mockItems} onUpdateStatus={onUpdateStatus} />);

    // Click on todo-03 (pending) -> should cycle to in_progress
    const cycleBtn = screen.getByTestId('cycle-status-btn-todo-03');
    fireEvent.click(cycleBtn);
    expect(onUpdateStatus).toHaveBeenCalledWith('todo-03', 'in_progress');
  });

  it('handles creating new plan item via form submission', async () => {
    const onCreateItem = vi.fn().mockResolvedValue(undefined);
    render(<TodoHudPanel sessionId="test-sess" items={mockItems} onCreateItem={onCreateItem} />);

    const titleInput = screen.getByTestId('new-todo-title-input');
    const assigneeInput = screen.getByTestId('new-todo-assignee-input');
    const addBtn = screen.getByTestId('add-todo-btn');

    expect(addBtn).toBeDisabled();

    fireEvent.change(titleInput, { target: { value: 'Deploy staging helm chart' } });
    fireEvent.change(assigneeInput, { target: { value: 'devops' } });
    expect(addBtn).not.toBeDisabled();

    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(onCreateItem).toHaveBeenCalledWith('Deploy staging helm chart', '', 'devops');
    });

    // Inputs should be reset
    expect(titleInput).toHaveValue('');
    expect(assigneeInput).toHaveValue('');
  });

  it('handles item deletion and clear all', () => {
    const onRemoveItem = vi.fn();
    const onClearAll = vi.fn();
    render(
      <TodoHudPanel
        sessionId="test-sess"
        items={mockItems}
        onRemoveItem={onRemoveItem}
        onClearAll={onClearAll}
      />
    );

    // Delete item 1
    const delBtn = screen.getByTestId('remove-todo-todo-01');
    fireEvent.click(delBtn);
    expect(onRemoveItem).toHaveBeenCalledWith('todo-01');

    // Clear all
    const clearBtn = screen.getByTestId('clear-all-todo-btn');
    fireEvent.click(clearBtn);
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it('handles expanding and collapsing list', () => {
    render(<TodoHudPanel sessionId="test-sess" items={mockItems} />);

    const toggleBtn = screen.getByTestId('toggle-expand-btn');
    expect(screen.getByTestId('todo-items-list')).toBeInTheDocument();

    // Click toggle to collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('todo-items-list')).not.toBeInTheDocument();

    // Click toggle to expand again
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('todo-items-list')).toBeInTheDocument();
  });
});
