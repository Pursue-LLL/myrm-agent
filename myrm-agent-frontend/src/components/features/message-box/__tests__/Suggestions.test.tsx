import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '@/store/useChatStore';

const { sendMessage } = vi.hoisted(() => ({ sendMessage: vi.fn() }));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { sendMessage: typeof sendMessage }) => unknown) => selector({ sendMessage }),
}));

import Suggestions from '../Suggestions';

function answer(suggestions?: string[]): Message {
  return {
    messageId: 'm-1',
    chatId: 'c-1',
    createdAt: new Date(0),
    content: 'Here is the answer.',
    role: 'assistant',
    suggestions,
  };
}

describe('Suggestions', () => {
  beforeEach(() => {
    sendMessage.mockClear();
  });

  it('lists every suggestion as a button under the answer', () => {
    render(<Suggestions message={answer(['How does it scale?', 'What does it cost?'])} loading={false} />);

    const buttons = screen.getAllByTestId('message-suggestion');
    expect(buttons.map((button) => button.textContent)).toEqual(['How does it scale?', 'What does it cost?']);
  });

  it('sends the clicked suggestion as the next message', () => {
    render(<Suggestions message={answer(['How does it scale?', 'What does it cost?'])} loading={false} />);

    fireEvent.click(screen.getAllByTestId('message-suggestion')[1]);

    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(sendMessage).toHaveBeenCalledWith('What does it cost?', undefined);
  });

  // The server answers [] when the last message only closes the conversation; that must leave the answer untouched.
  it('draws nothing when the model offered no follow-up', () => {
    const { container } = render(<Suggestions message={answer([])} loading={false} />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('message-suggestions')).toBeNull();
  });

  it('draws nothing before any follow-up was requested', () => {
    const { container } = render(<Suggestions message={answer()} loading={false} />);

    expect(container.firstChild).toBeNull();
  });

  it('draws nothing while the answer is still streaming', () => {
    const { container } = render(<Suggestions message={answer(['How does it scale?'])} loading />);

    expect(container.firstChild).toBeNull();
  });
});
