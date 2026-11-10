import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ForkButton } from '../ForkButton';

const hoisted = vi.hoisted(() => ({ fork: vi.fn() }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/hooks/shared/useToast', () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock('@/services/fork-api', () => ({ forkConversation: (...args: unknown[]) => hoisted.fork(...args) }));

const button = () => screen.getByRole('button', { name: 'Fork conversation from this message' });

beforeEach(() => {
  vi.resetAllMocks();
  hoisted.fork.mockResolvedValue({ success: true, data: { new_chat_id: 'c2', parent_chat_id: 'c1', fork_point: 2 } });
});

describe('ForkButton', () => {
  it('is a labelled button with no dialog until it is pressed', () => {
    render(<ForkButton chatId="chat-1" messageIndex={2} />);

    expect(button()).toHaveAttribute('title', 'Fork conversation');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens the dialog for its own message and leaves it again from Cancel', () => {
    render(<ForkButton chatId="chat-1" messageIndex={2} />);

    fireEvent.click(button());
    expect(screen.getByRole('dialog')).toHaveTextContent('branch from message #3,');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('forks the chat and message it was given', async () => {
    render(<ForkButton chatId="chat-7" messageIndex={0} />);

    fireEvent.click(button());
    fireEvent.click(screen.getByRole('button', { name: 'Create Now' }));

    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledWith('chat-7', 0, undefined, 'full_clone', undefined));
  });

  it('starts every opening from a clean form', () => {
    render(<ForkButton chatId="chat-1" messageIndex={2} />);
    fireEvent.click(button());
    fireEvent.change(screen.getByLabelText('New Conversation Title'), { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('button', { name: /Independent Acceptance Task/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    fireEvent.click(button());

    expect(screen.getByLabelText('New Conversation Title')).toHaveValue('');
    expect(screen.getByRole('button', { name: /Regular Branch/ })).toHaveAttribute('aria-pressed', 'true');
  });
});
