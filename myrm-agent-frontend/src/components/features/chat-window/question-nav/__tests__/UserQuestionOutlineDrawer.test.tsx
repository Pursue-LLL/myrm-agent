import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UserQuestionOutlineDrawer } from '../UserQuestionOutlineDrawer';
import { useUserQuestionNavStore } from '../useUserQuestionNavStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('UserQuestionOutlineDrawer', () => {
  const onJumpMock = vi.fn();
  const onCloseMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useUserQuestionNavStore.getState().reset();
  });

  it('renders nothing when isOutlineOpen is false', () => {
    useUserQuestionNavStore.getState().setOutlineOpen(false);
    const { container } = render(
      <UserQuestionOutlineDrawer
        onJumpToMessageIndex={onJumpMock}
        onClose={onCloseMock}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header and empty state when there are no questions', () => {
    useUserQuestionNavStore.getState().setOutlineOpen(true);
    render(
      <UserQuestionOutlineDrawer
        onJumpToMessageIndex={onJumpMock}
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('outlineDrawerTitle')).toBeInTheDocument();
    expect(screen.getByText('noQuestionsYet')).toBeInTheDocument();
  });

  it('renders question items and triggers jump upon clicking a question', () => {
    useUserQuestionNavStore.getState().syncMessages([
      { messageId: 'm1', role: 'user', content: 'First design principle' },
      { messageId: 'm2', role: 'assistant', content: 'Detail explanation' },
      { messageId: 'm3', role: 'user', content: 'Second requirement' },
    ]);
    useUserQuestionNavStore.getState().setOutlineOpen(true);

    render(
      <UserQuestionOutlineDrawer
        onJumpToMessageIndex={onJumpMock}
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('First design principle')).toBeInTheDocument();
    expect(screen.getByText('Second requirement')).toBeInTheDocument();

    // Click the second question item
    const secondItemBtn = screen.getByText('Second requirement').closest('button');
    expect(secondItemBtn).not.toBeNull();
    if (secondItemBtn) {
      fireEvent.click(secondItemBtn);
    }

    expect(onJumpMock).toHaveBeenCalledWith(2, 'm3');
    expect(useUserQuestionNavStore.getState().currentIndex).toBe(1);
    expect(useUserQuestionNavStore.getState().isOutlineOpen).toBe(false);
    expect(onCloseMock).toHaveBeenCalledOnce();
  });

  it('closes drawer when clicking close button', () => {
    useUserQuestionNavStore.getState().setOutlineOpen(true);
    render(
      <UserQuestionOutlineDrawer
        onJumpToMessageIndex={onJumpMock}
        onClose={onCloseMock}
      />
    );

    const closeBtn = screen.getByLabelText('closeDrawer');
    fireEvent.click(closeBtn);

    expect(useUserQuestionNavStore.getState().isOutlineOpen).toBe(false);
    expect(onCloseMock).toHaveBeenCalledOnce();
  });
});
