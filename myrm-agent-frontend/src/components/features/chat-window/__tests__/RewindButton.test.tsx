import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useRewindStore } from '@/store/chat/useRewindStore';

import { RewindButton } from '../RewindButton';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

const button = () => screen.getByRole('button', { name: 'Rewind to here' });

beforeEach(() => {
  useRewindStore.setState({ target: null });
});

describe('RewindButton', () => {
  it('asks to rewind to its own message', () => {
    render(<RewindButton chatId="chat-1" messageId="m-3" messageIndex={2} />);

    expect(button()).toHaveAttribute('title', 'Rewind conversation to here');
    fireEvent.click(button());

    expect(useRewindStore.getState().target).toEqual({ chatId: 'chat-1', messageId: 'm-3', messageIndex: 2 });
  });

  it('keeps the click to itself: no parent handler runs and no link or form is followed', () => {
    const onParentClick = vi.fn();
    render(
      <div role="presentation" onClick={onParentClick}>
        <RewindButton chatId="chat-1" messageId="m-3" messageIndex={2} />
      </div>,
    );

    const notPrevented = fireEvent.click(button());

    expect(notPrevented).toBe(false);
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it('cannot be pressed while the agent works, and says why', () => {
    render(<RewindButton chatId="chat-1" messageId="m-3" messageIndex={2} disabled />);

    expect(button()).toBeDisabled();
    expect(button()).toHaveAttribute('title', 'Rewind is unavailable while the agent is working');
    fireEvent.click(button());

    expect(useRewindStore.getState().target).toBeNull();
  });
});
