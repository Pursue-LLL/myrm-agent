import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SiblingNav from '../SiblingNav';

const mocks = vi.hoisted(() => ({
  getSiblings: vi.fn(),
  switchSibling: vi.fn(),
  loadMessages: vi.fn(),
  fetchPlan: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  getSiblings: mocks.getSiblings,
  switchSibling: mocks.switchSibling,
}));
vi.mock('@/store/useChatStore', () => ({
  default: (select: (state: { loadMessages: typeof mocks.loadMessages }) => unknown) =>
    select({ loadMessages: mocks.loadMessages }),
}));
vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ fetchPlan: mocks.fetchPlan }) },
}));

// The global next-intl stub renders every translation key as itself.
const PREVIOUS = 'previous';
const NEXT = 'next';

const renderNav = (siblingIndex: number, siblingCount: number) =>
  render(<SiblingNav chatId="c-1" siblingGroupId="g-1" siblingIndex={siblingIndex} siblingCount={siblingCount} />);

describe('SiblingNav', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when the group has a single variant', () => {
    const { container } = renderNav(1, 1);

    expect(container.firstChild).toBeNull();
  });

  it('names both arrows through the localized labels', () => {
    renderNav(2, 3);

    expect(screen.getByRole('button', { name: PREVIOUS })).not.toBeNull();
    expect(screen.getByRole('button', { name: NEXT })).not.toBeNull();
    expect(screen.getByText('2/3')).not.toBeNull();
  });

  it('disables the arrow that has nowhere to go', () => {
    const { unmount } = renderNav(1, 3);
    expect((screen.getByRole('button', { name: PREVIOUS }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: NEXT }) as HTMLButtonElement).disabled).toBe(false);
    unmount();

    renderNav(3, 3);
    expect((screen.getByRole('button', { name: NEXT }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('switches to the following variant and reloads the conversation', async () => {
    mocks.getSiblings.mockResolvedValue({
      siblings: [
        { id: 'm-1', is_active: false },
        { id: 'm-2', is_active: true },
        { id: 'm-3', is_active: false },
      ],
    });
    mocks.switchSibling.mockResolvedValue({ success: true });
    mocks.loadMessages.mockResolvedValue(undefined);
    renderNav(2, 3);

    fireEvent.click(screen.getByRole('button', { name: NEXT }));

    await waitFor(() => expect(mocks.loadMessages).toHaveBeenCalledWith('c-1'));
    expect(mocks.switchSibling).toHaveBeenCalledWith('c-1', 'g-1', 'm-3');
    expect(mocks.fetchPlan).toHaveBeenCalledWith('c-1');
  });
});
