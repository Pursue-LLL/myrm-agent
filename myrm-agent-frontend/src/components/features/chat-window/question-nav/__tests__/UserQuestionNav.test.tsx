import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UserQuestionNav } from '../UserQuestionNav';
import { useUserQuestionNavStore } from '../useUserQuestionNavStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe('UserQuestionNav', () => {
  const onJumpMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useUserQuestionNavStore.getState().reset();
  });

  it('renders nothing when there is only 1 or 0 user question', () => {
    const { container, rerender } = render(
      <UserQuestionNav onJumpToMessageIndex={onJumpMock} />
    );
    expect(container.firstChild).toBeNull();

    // 1 user question
    act(() => {
      useUserQuestionNavStore.getState().syncMessages([
        { messageId: 'm1', role: 'user', content: 'Single prompt' },
      ]);
    });
    rerender(<UserQuestionNav onJumpToMessageIndex={onJumpMock} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders when visible=true and there are >= 2 questions', () => {
    useUserQuestionNavStore.getState().syncMessages([
      { messageId: 'm1', role: 'user', content: 'Prompt 1' },
      { messageId: 'm2', role: 'assistant', content: 'Reply 1' },
      { messageId: 'm3', role: 'user', content: 'Prompt 2' },
    ]);

    render(<UserQuestionNav onJumpToMessageIndex={onJumpMock} />);
    expect(screen.getByLabelText('User Question Navigation HUD')).toBeInTheDocument();
    expect(screen.getByText('1/2')).toBeInTheDocument();
  });

  it('disables previous button on the first question and allows jumping to next', () => {
    useUserQuestionNavStore.getState().syncMessages([
      { messageId: 'm1', role: 'user', content: 'Prompt 1' },
      { messageId: 'm2', role: 'assistant', content: 'Reply 1' },
      { messageId: 'm3', role: 'user', content: 'Prompt 2' },
    ]);

    render(<UserQuestionNav onJumpToMessageIndex={onJumpMock} />);

    const prevBtn = screen.getByLabelText('prevQuestionAria');
    const nextBtn = screen.getByLabelText('nextQuestionAria');

    expect(prevBtn).toBeDisabled();
    expect(nextBtn).not.toBeDisabled();

    // Click Next
    fireEvent.click(nextBtn);
    expect(onJumpMock).toHaveBeenCalledWith(2, 'm3');
    expect(useUserQuestionNavStore.getState().currentIndex).toBe(1);
  });

  it('disables next button on the last question and allows jumping to previous', () => {
    useUserQuestionNavStore.getState().syncMessages([
      { messageId: 'm1', role: 'user', content: 'Prompt 1' },
      { messageId: 'm2', role: 'assistant', content: 'Reply 1' },
      { messageId: 'm3', role: 'user', content: 'Prompt 2' },
    ]);
    useUserQuestionNavStore.getState().setCurrentIndex(1);

    render(<UserQuestionNav onJumpToMessageIndex={onJumpMock} />);

    const prevBtn = screen.getByLabelText('prevQuestionAria');
    const nextBtn = screen.getByLabelText('nextQuestionAria');

    expect(prevBtn).not.toBeDisabled();
    expect(nextBtn).toBeDisabled();

    // Click Previous
    fireEvent.click(prevBtn);
    expect(onJumpMock).toHaveBeenCalledWith(0, 'm1');
    expect(useUserQuestionNavStore.getState().currentIndex).toBe(0);
  });

  it('opens outline drawer when clicking the indicator button', () => {
    useUserQuestionNavStore.getState().syncMessages([
      { messageId: 'm1', role: 'user', content: 'Prompt 1' },
      { messageId: 'm2', role: 'assistant', content: 'Reply 1' },
      { messageId: 'm3', role: 'user', content: 'Prompt 2' },
    ]);

    render(<UserQuestionNav onJumpToMessageIndex={onJumpMock} />);

    const outlineBtn = screen.getByLabelText('openOutlineAria');
    fireEvent.click(outlineBtn);

    expect(useUserQuestionNavStore.getState().isOutlineOpen).toBe(true);
  });
});
