'use client';

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ScrollToBottomButton from '../ScrollToBottomButton';
import type { PendingCountCueItem } from '../question-nav/userQuestionNavTypes';

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => (key: string) => `${ns}.${key}`,
}));

describe('ScrollToBottomButton with exact pending-count cue', () => {
  const defaultProps = {
    visible: true,
    hasNewMessage: false,
    onClick: vi.fn(),
  };

  it('renders exact pending count in badge when pendingCount > 0', () => {
    render(
      <ScrollToBottomButton
        {...defaultProps}
        pendingCount={7}
      />
    );

    expect(screen.getByText('7 chat.scrollCue.newMessage')).toBeInTheDocument();
  });

  it('renders progressive disclosure preview items when pendingItems are provided', () => {
    const items: PendingCountCueItem[] = [
      { messageId: '1', role: 'assistant', snippet: 'Generated report section' },
      { messageId: '2', role: 'user', snippet: 'Please clarify edge case' },
    ];

    render(
      <ScrollToBottomButton
        {...defaultProps}
        pendingCount={2}
        pendingItems={items}
      />
    );

    expect(screen.getByText('Generated report section')).toBeInTheDocument();
    expect(screen.getByText('Please clarify edge case')).toBeInTheDocument();
    expect(screen.queryByText(/\+.*more/)).not.toBeInTheDocument();
  });

  it('renders +N more summary when pendingCount exceeds 3', () => {
    const items: PendingCountCueItem[] = [
      { messageId: '1', role: 'assistant', snippet: 'Step 1 output' },
      { messageId: '2', role: 'assistant', snippet: 'Step 2 output' },
      { messageId: '3', role: 'user', snippet: 'Followup prompt' },
    ];

    render(
      <ScrollToBottomButton
        {...defaultProps}
        pendingCount={9}
        pendingItems={items}
      />
    );

    expect(screen.getByText('+6 more')).toBeInTheDocument();
  });

  it('calls onClick handler when clicked', () => {
    const onClick = vi.fn();
    render(
      <ScrollToBottomButton
        {...defaultProps}
        onClick={onClick}
        pendingCount={3}
      />
    );

    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
