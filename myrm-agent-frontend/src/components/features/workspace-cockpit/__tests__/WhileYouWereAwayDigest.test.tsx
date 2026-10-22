import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WhileYouWereAwayDigest } from '../WhileYouWereAwayDigest';
import type { OfflineDigestSummary } from '../workspaceCockpitTypes';

describe('WhileYouWereAwayDigest', () => {
  const mockSummary: OfflineDigestSummary = {
    awayDurationMs: 3600 * 1000 * 3, // 3h
    completedGoalsCount: 4,
    failedTasksCount: 1,
    pendingDecisionsCount: 2,
    inProgressCount: 5,
    highlights: [
      {
        id: 'h-1',
        title: 'Approve production deployment token',
        type: 'decision',
        timeAgo: '15m',
        chatId: 'chat-approval-1',
      },
      {
        id: 'h-2',
        title: 'Compilation failed on assets bundle',
        type: 'failure',
        timeAgo: '45m',
        chatId: 'chat-fail-1',
      },
      {
        id: 'h-3',
        title: 'Delivered refactored auth flow',
        type: 'success',
        timeAgo: '1h',
        chatId: 'chat-success-1',
      },
    ],
  };

  it('renders away duration and 4 metrics cards', () => {
    const onDismiss = vi.fn();
    const onNavigateToTask = vi.fn();

    render(
      <WhileYouWereAwayDigest
        summary={mockSummary}
        onDismiss={onDismiss}
        onNavigateToTask={onNavigateToTask}
      />,
    );

    expect(screen.getByTestId('while-you-were-away-digest')).toBeInTheDocument();
    expect(screen.getByText(/While You Were Away/i)).toBeInTheDocument();
    expect(screen.getByText('(3h 0m)')).toBeInTheDocument();

    expect(screen.getByTestId('digest-metric-decisions')).toHaveTextContent('2');
    expect(screen.getByTestId('digest-metric-in-progress')).toHaveTextContent('5');
    expect(screen.getByTestId('digest-metric-completed')).toHaveTextContent('4');
    expect(screen.getByTestId('digest-metric-failed')).toHaveTextContent('1');
  });

  it('renders highlights and navigates to chat when clicked', () => {
    const onDismiss = vi.fn();
    const onNavigateToTask = vi.fn();

    render(
      <WhileYouWereAwayDigest
        summary={mockSummary}
        onDismiss={onDismiss}
        onNavigateToTask={onNavigateToTask}
      />,
    );

    const highlightItem = screen.getByText('Approve production deployment token');
    expect(highlightItem).toBeInTheDocument();

    fireEvent.click(highlightItem);
    expect(onNavigateToTask).toHaveBeenCalledWith('chat-approval-1', 'h-1');
  });

  it('calls onDismiss when close button is clicked', () => {
    const onDismiss = vi.fn();
    const onNavigateToTask = vi.fn();

    render(
      <WhileYouWereAwayDigest
        summary={mockSummary}
        onDismiss={onDismiss}
        onNavigateToTask={onNavigateToTask}
      />,
    );

    const dismissBtn = screen.getByTestId('digest-dismiss-btn');
    fireEvent.click(dismissBtn);

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
