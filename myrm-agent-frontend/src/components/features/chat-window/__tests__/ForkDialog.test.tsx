import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ForkConversationResponse } from '@/services/fork-api';
import useChatStore from '@/store/useChatStore';
import { deferred } from '@/test-utils/deferred';

import { ForkDialog } from '../ForkDialog';

const hoisted = vi.hoisted(() => ({ push: vi.fn(), toast: vi.fn(), fork: vi.fn() }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: hoisted.push }) }));
vi.mock('@/hooks/shared/useToast', () => ({ useToast: () => ({ toast: hoisted.toast }) }));
vi.mock('@/services/fork-api', () => ({ forkConversation: (...args: unknown[]) => hoisted.fork(...args) }));

const forked = (newChatId = 'chat-2'): ForkConversationResponse => ({
  success: true,
  data: { new_chat_id: newChatId, parent_chat_id: 'chat-1', fork_point: 4 },
});

function renderDialog() {
  const onOpenChange = vi.fn();
  render(<ForkDialog open onOpenChange={onOpenChange} chatId="chat-1" messageIndex={4} />);
  return onOpenChange;
}

const create = () => screen.getByRole('button', { name: /Create Now|Creating/ });
const cancel = () => screen.getByRole('button', { name: 'Cancel' });
const regularBranch = () => screen.getByRole('button', { name: /Regular Branch/ });
const acceptance = () => screen.getByRole('button', { name: /Independent Acceptance Task/ });
const titleInput = () => screen.getByLabelText('New Conversation Title');
const scopeInput = () => screen.getByLabelText(/Audit Focus/);
const dialog = () => screen.getByRole('dialog');

beforeEach(() => {
  vi.resetAllMocks();
  useChatStore.setState({ loading: false });
});

describe('ForkDialog form', () => {
  it('names the message in people numbers, from 1', () => {
    renderDialog();

    expect(screen.getByText(/branch from message #5,/)).toBeInTheDocument();
  });

  it('starts as a regular branch without the acceptance scope field', () => {
    renderDialog();

    expect(regularBranch()).toHaveAttribute('aria-pressed', 'true');
    expect(acceptance()).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByLabelText(/Audit Focus/)).toBeNull();
  });

  it('shows the scope field only for an acceptance task and says which mode is picked', () => {
    renderDialog();

    fireEvent.click(acceptance());

    expect(acceptance()).toHaveAttribute('aria-pressed', 'true');
    expect(regularBranch()).toHaveAttribute('aria-pressed', 'false');
    expect(scopeInput()).toBeInTheDocument();

    fireEvent.click(regularBranch());

    expect(screen.queryByLabelText(/Audit Focus/)).toBeNull();
  });

  it('closes from Cancel and from Escape while idle, and keeps the built-in close button', () => {
    const onOpenChange = renderDialog();

    fireEvent.click(cancel());
    fireEvent.keyDown(dialog(), { key: 'Escape' });

    expect(onOpenChange).toHaveBeenCalledTimes(2);
    expect(onOpenChange).toHaveBeenNthCalledWith(1, false);
    expect(onOpenChange).toHaveBeenNthCalledWith(2, false);
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });
});

describe('ForkDialog what it sends', () => {
  beforeEach(() => hoisted.fork.mockResolvedValue(forked()));

  it('forks as a regular branch with no title or scope when none is given', async () => {
    renderDialog();

    fireEvent.click(create());

    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledTimes(1));
    expect(hoisted.fork).toHaveBeenCalledWith('chat-1', 4, undefined, 'full_clone', undefined);
  });

  it('sends the title without the spaces around it, and none at all when it is only spaces', async () => {
    renderDialog();

    fireEvent.change(titleInput(), { target: { value: '  Plan B  ' } });
    fireEvent.click(create());
    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledTimes(1));
    expect(hoisted.fork).toHaveBeenLastCalledWith('chat-1', 4, 'Plan B', 'full_clone', undefined);

    fireEvent.change(titleInput(), { target: { value: '   ' } });
    fireEvent.click(create());
    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledTimes(2));
    expect(hoisted.fork).toHaveBeenLastCalledWith('chat-1', 4, undefined, 'full_clone', undefined);
  });

  it('sends the acceptance scope, trimmed, only for an acceptance task', async () => {
    renderDialog();
    fireEvent.click(acceptance());
    fireEvent.change(scopeInput(), { target: { value: '  edge cases  ' } });

    fireEvent.click(create());
    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledTimes(1));
    expect(hoisted.fork).toHaveBeenLastCalledWith('chat-1', 4, undefined, 'acceptance_verifier', 'edge cases');

    fireEvent.change(scopeInput(), { target: { value: '   ' } });
    fireEvent.click(create());
    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledTimes(2));
    expect(hoisted.fork).toHaveBeenLastCalledWith('chat-1', 4, undefined, 'acceptance_verifier', undefined);

    fireEvent.change(scopeInput(), { target: { value: 'left over' } });
    fireEvent.click(regularBranch());
    fireEvent.click(create());
    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledTimes(3));
    expect(hoisted.fork).toHaveBeenLastCalledWith('chat-1', 4, undefined, 'full_clone', undefined);
  });

  it('forks on Enter in the title, except for an acceptance task', async () => {
    renderDialog();

    fireEvent.keyDown(titleInput(), { key: 'a' });
    expect(hoisted.fork).not.toHaveBeenCalled();
    fireEvent.keyDown(titleInput(), { key: 'Enter' });
    await vi.waitFor(() => expect(hoisted.fork).toHaveBeenCalledTimes(1));

    fireEvent.click(acceptance());
    fireEvent.keyDown(titleInput(), { key: 'Enter' });
    await act(async () => undefined);
    expect(hoisted.fork).toHaveBeenCalledTimes(1);
  });
});

describe('ForkDialog while the fork is being made', () => {
  it('shows it is busy, cannot be dismissed, and goes to the new chat when done', async () => {
    const pending = deferred<ForkConversationResponse>();
    hoisted.fork.mockReturnValue(pending.promise);
    const onOpenChange = renderDialog();

    fireEvent.click(create());

    expect(create()).toHaveTextContent('Creating...');
    expect(create()).toBeDisabled();
    expect(cancel()).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Close' })).toBeNull();
    fireEvent.keyDown(dialog(), { key: 'Escape' });
    fireEvent.keyDown(titleInput(), { key: 'Enter' });
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(hoisted.fork).toHaveBeenCalledTimes(1);

    await act(async () => pending.resolve(forked('chat-9')));

    expect(hoisted.toast).toHaveBeenCalledWith({
      title: 'Conversation forked successfully',
      description: 'New branch created from message #5',
    });
    expect(hoisted.push).toHaveBeenCalledWith('/chat-9');
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
  });
});

describe('ForkDialog when it cannot fork', () => {
  const failure = (description: string) => ({
    title: 'Fork failed',
    description,
    variant: 'destructive',
  });

  it('refuses while the agent is answering and sends nothing', async () => {
    useChatStore.setState({ loading: true });
    renderDialog();

    fireEvent.click(create());

    expect(hoisted.toast).toHaveBeenCalledWith(failure('Cannot fork while the agent is responding'));
    expect(hoisted.fork).not.toHaveBeenCalled();
    expect(create()).toBeEnabled();
  });

  it('reports the reason and stays open, ready to try again', async () => {
    hoisted.fork.mockRejectedValue(new Error('Parent conversation not found'));
    const onOpenChange = renderDialog();

    fireEvent.click(create());

    await vi.waitFor(() => expect(hoisted.toast).toHaveBeenCalledWith(failure('Parent conversation not found')));
    expect(hoisted.push).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(create()).toBeEnabled();
    expect(cancel()).toBeEnabled();
  });

  it('does not make up a reason for a failure that has none', async () => {
    hoisted.fork.mockRejectedValue('boom');
    renderDialog();

    fireEvent.click(create());

    await vi.waitFor(() => expect(hoisted.toast).toHaveBeenCalledWith(failure('Unknown error occurred')));
  });

  it('treats an answer without a new chat as a failure with a different reason than its title', async () => {
    hoisted.fork.mockResolvedValue({ success: false, data: null });
    renderDialog();

    fireEvent.click(create());

    await vi.waitFor(() => expect(hoisted.toast).toHaveBeenCalledWith(failure('Unknown error occurred')));
    expect(hoisted.push).not.toHaveBeenCalled();
  });
});
