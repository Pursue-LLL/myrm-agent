import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ExtensionWidgetHost } from '../ExtensionWidgetHost';

const mockTranslations = (key: string) => {
  const map: Record<string, string> = {
    nanoContextTitle: 'Nano-Context',
    todoTitle: 'Active Todo List',
    newTodoPlaceholder: 'Add task...',
    turns: 'turns',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('ExtensionWidgetHost', () => {
  const dummyNano = {
    usedTokens: 25000,
    maxTokens: 100000,
    percentage: 25.0,
    turnCount: 5,
    modelName: 'claude-3-7-sonnet',
  };

  it('renders Nano-Context widget and context data', () => {
    render(<ExtensionWidgetHost nanoContext={dummyNano} />);

    expect(screen.getByTestId('extension-widget-host')).toBeInTheDocument();
    expect(screen.getByText(/Nano-Context/i)).toBeInTheDocument();
    expect(screen.getAllByText(/25%/)[0]).toBeInTheDocument();
    expect(screen.getByText('claude-3-7-sonnet')).toBeInTheDocument();
    expect(screen.getByText(/5 turns/i)).toBeInTheDocument();
  });

  it('toggles collapsible panels on button click', () => {
    render(<ExtensionWidgetHost nanoContext={dummyNano} />);

    const nanoToggle = screen.getByRole('button', { name: /Nano-Context/i });
    fireEvent.click(nanoToggle);
    expect(screen.queryByText('claude-3-7-sonnet')).not.toBeInTheDocument();

    fireEvent.click(nanoToggle);
    expect(screen.getByText('claude-3-7-sonnet')).toBeInTheDocument();
  });

  it('handles todo item toggle, addition and deletion', () => {
    const initialTodos = [
      { id: 't-1', text: 'Write regression tests', done: false },
    ];
    render(<ExtensionWidgetHost initialTodos={initialTodos} />);

    expect(screen.getByText('Write regression tests')).toBeInTheDocument();

    // Toggle complete
    const todoBtn = screen.getByRole('button', { name: /Write regression tests/i });
    fireEvent.click(todoBtn);
    expect(screen.getByText('Write regression tests')).toHaveClass('line-through');

    // Add new todo
    const input = screen.getByPlaceholderText(/Add task.../i);
    fireEvent.change(input, { target: { value: 'Publish release artifacts' } });
    const addBtn = screen.getByRole('button', { name: 'Add' });
    fireEvent.click(addBtn);

    expect(screen.getByText('Publish release artifacts')).toBeInTheDocument();

    // Delete todo
    const deleteBtns = screen.getAllByRole('button', { name: 'Delete todo' });
    fireEvent.click(deleteBtns[0]);
    expect(screen.queryByText('Write regression tests')).not.toBeInTheDocument();
  });
});
