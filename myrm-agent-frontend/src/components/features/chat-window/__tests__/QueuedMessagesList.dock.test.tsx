import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueuedMessagesList } from '../QueuedMessagesList';
import type { QueuedMessage } from '@/store/chat/useMessageQueueStore';

describe('QueuedMessagesList dock controls and keyboard interaction', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  const mockQueue: QueuedMessage[] = [
    {
      id: 'q-1',
      text: 'First queued instruction for tests',
      files: [],
      timestamp: 1000,
    },
    {
      id: 'q-2',
      text: 'Second queued instruction for tests',
      files: [],
      timestamp: 2000,
    },
    {
      id: 'q-3',
      text: 'Third queued instruction for tests',
      files: [],
      timestamp: 3000,
    },
  ];

  function renderDockList(props: Partial<React.ComponentProps<typeof QueuedMessagesList>> = {}) {
    const defaultProps: React.ComponentProps<typeof QueuedMessagesList> = {
      queue: mockQueue,
      pausedReason: null,
      editingId: null,
      setEditingId: vi.fn(),
      editMessage: vi.fn(),
      removeMessage: vi.fn(),
      reorder: vi.fn(),
      resume: vi.fn(),
      chatId: 'chat-dock-test',
      onClearQueue: vi.fn(),
      onPause: vi.fn(),
      ...props,
    };

    return {
      ...render(<QueuedMessagesList {...defaultProps} />),
      props: defaultProps,
    };
  }

  it('renders dock header bar with queue count and items list by default', () => {
    renderDockList();

    expect(screen.getByTestId('queue-dock-header')).toBeInTheDocument();
    expect(screen.getByText('Queued (3)')).toBeInTheDocument();
    expect(screen.getByRole('list')).toBeInTheDocument();
  });

  it('toggles collapse state and shows next preview when collapsed', () => {
    renderDockList();

    const toggleBtn = screen.getByTestId('queue-dock-toggle');
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');

    // Click to collapse
    fireEvent.click(toggleBtn);

    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByTestId('queue-collapsed-preview')).toHaveTextContent(
      'Next: "First queued instruction for tests"',
    );
    expect(screen.queryByRole('list')).not.toBeInTheDocument();

    // Click again to expand
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('list')).toBeInTheDocument();
  });

  it('handles global Escape to trigger onPause and auto-expand dock', () => {
    const onPause = vi.fn();
    renderDockList({ onPause });

    const toggleBtn = screen.getByTestId('queue-dock-toggle');
    // First collapse it
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');

    // Fire Escape keydown on window
    fireEvent.keyDown(window, { key: 'Escape' });

    expect(onPause).toHaveBeenCalledTimes(1);
    // Dock should now be auto-expanded
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('list')).toBeInTheDocument();
  });

  it('triggers onClearQueue when trash button is clicked', () => {
    const onClearQueue = vi.fn();
    renderDockList({ onClearQueue });

    const clearBtn = screen.getByTestId('queue-clear-all');
    fireEvent.click(clearBtn);

    expect(onClearQueue).toHaveBeenCalledTimes(1);
  });

  it('triggers reorder(index, 0) when move to top button is clicked on second item', () => {
    const reorder = vi.fn();
    renderDockList({ reorder });

    const moveToTopButtons = screen.getAllByTestId(/queue-move-to-top/);
    expect(moveToTopButtons.length).toBeGreaterThan(0);

    fireEvent.click(moveToTopButtons[0]);
    // The second item (index 1) moved to top (index 0)
    expect(reorder).toHaveBeenCalledWith(1, 0);
  });

  it('shows paused badge in dock header when queue is paused', () => {
    renderDockList({ pausedReason: 'stopped' });

    expect(screen.getByTestId('queue-paused-badge')).toBeInTheDocument();
    expect(screen.getByTestId('queue-paused-badge')).toHaveTextContent('Paused');
  });
});
