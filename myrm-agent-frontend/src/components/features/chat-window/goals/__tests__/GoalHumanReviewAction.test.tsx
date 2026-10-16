// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { chat, showI18nToast } = vi.hoisted(() => ({
  chat: {
    inputMessage: '',
    sendMessage: vi.fn<(input: string) => Promise<boolean>>(),
    setInputMessage: vi.fn<(message: string) => void>(),
  },
  showI18nToast: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({ default: { getState: () => chat } }));
vi.mock('@/services/i18nToastService', () => ({ showI18nToast }));

import { GoalHumanReviewAction } from '../GoalHumanReviewAction';

const t = ((key: string) => key) as unknown as Parameters<typeof GoalHumanReviewAction>[0]['t'];
const busyError = () => Object.assign(new Error('busy'), { name: 'AgentBusyError' });

function setup(serverTakesIt = true) {
  const onAction = vi
    .fn<(action: 'approve' | 'reject', note?: string) => Promise<boolean>>()
    .mockResolvedValue(serverTakesIt);
  render(<GoalHumanReviewAction onAction={onAction} t={t} />);
  return { onAction, input: screen.getByPlaceholderText('feedbackPlaceholder') as HTMLInputElement };
}

function type(input: HTMLInputElement, value: string): void {
  fireEvent.change(input, { target: { value } });
}

const flush = () => act(async () => undefined);

describe('GoalHumanReviewAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chat.inputMessage = '';
    chat.sendMessage.mockResolvedValue(true);
  });

  it('sends the goal back to work with the feedback, then sends the feedback and empties the box', async () => {
    const { onAction, input } = setup();
    type(input, 'use the staging database');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(chat.sendMessage).toHaveBeenCalledWith('use the staging database'));
    expect(onAction).toHaveBeenCalledWith('reject', 'use the staging database');
    expect(input).toHaveValue('');
    // The agent reads only an active goal: the goal is back at work before the feedback turn starts.
    expect(onAction.mock.invocationCallOrder[0]).toBeLessThan(chat.sendMessage.mock.invocationCallOrder[0]);
  });

  it('uses the retries-reset message when the box is empty, from the button as well', async () => {
    const { onAction } = setup();

    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() => expect(chat.sendMessage).toHaveBeenCalledWith('resetRetriesMessage'));
    expect(onAction).toHaveBeenCalledWith('reject', 'resetRetriesMessage');
  });

  it('keeps the text in the box and sends nothing when the server did not take the reject, so it can be edited', async () => {
    const { onAction, input } = setup();
    onAction.mockResolvedValueOnce(false);
    type(input, 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(onAction).toHaveBeenCalledTimes(1));
    await flush();

    expect(chat.sendMessage).not.toHaveBeenCalled();
    expect(input).toHaveValue('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    type(input, 'use the key from the vault');
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(chat.sendMessage).toHaveBeenCalledWith('use the key from the vault'));
  });

  it('puts the feedback into an empty composer when the agent did not take it', async () => {
    chat.sendMessage.mockResolvedValue(false);
    const { input } = setup();
    type(input, 'try the other branch');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(chat.setInputMessage).toHaveBeenCalledWith('try the other branch'));
    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('leaves a composer that already holds text alone', async () => {
    chat.inputMessage = 'something else I was writing';
    chat.sendMessage.mockResolvedValue(false);
    const { input } = setup();
    type(input, 'try the other branch');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(chat.sendMessage).toHaveBeenCalledTimes(1));
    await flush();
    expect(chat.setInputMessage).not.toHaveBeenCalled();
  });

  it('tells the user the agent is busy and returns the feedback to the composer when the server refuses the turn', async () => {
    chat.sendMessage.mockRejectedValue(busyError());
    const { input } = setup();
    type(input, 'try again');

    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() =>
      expect(showI18nToast).toHaveBeenCalledWith(
        'chat.sendBlocked.title',
        undefined,
        expect.objectContaining({ descriptionKey: 'chat.sendBlocked.busyDescription' }),
      ),
    );
    expect(chat.setInputMessage).toHaveBeenCalledWith('try again');
  });

  it('reports any other failure with the generic notice and returns the feedback to the composer', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    chat.sendMessage.mockRejectedValue(new Error('boom'));
    const { input } = setup();
    type(input, 'try again');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() =>
      expect(showI18nToast).toHaveBeenCalledWith(
        'chat.messageFailed.title',
        undefined,
        expect.objectContaining({ descriptionKey: 'chat.messageFailed.generic' }),
      ),
    );
    expect(chat.setInputMessage).toHaveBeenCalledWith('try again');
    consoleError.mockRestore();
  });

  it('rejects once however often it is submitted while the request is out', async () => {
    const { onAction, input } = setup();
    type(input, 'go on');

    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() => expect(chat.sendMessage).toHaveBeenCalledTimes(1));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('keeps text typed while the request was out', async () => {
    const { onAction, input } = setup();
    let answer: (taken: boolean) => void = () => undefined;
    onAction.mockReturnValueOnce(new Promise<boolean>((resolve) => (answer = resolve)));
    type(input, 'first');
    fireEvent.keyDown(input, { key: 'Enter' });

    type(input, 'first, and also this');
    answer(true);

    await waitFor(() => expect(chat.sendMessage).toHaveBeenCalledWith('first'));
    expect(input).toHaveValue('first, and also this');
  });

  it('ignores the Enter that confirms an input-method candidate', () => {
    const { onAction, input } = setup();
    type(input, 'ni hao');

    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });

    expect(onAction).not.toHaveBeenCalled();
    expect(chat.sendMessage).not.toHaveBeenCalled();
  });

  it('approves without sending anything', () => {
    const { onAction } = setup();

    fireEvent.click(screen.getByRole('button', { name: 'forceApprove' }));

    expect(onAction).toHaveBeenCalledWith('approve');
    expect(chat.sendMessage).not.toHaveBeenCalled();
  });
});
