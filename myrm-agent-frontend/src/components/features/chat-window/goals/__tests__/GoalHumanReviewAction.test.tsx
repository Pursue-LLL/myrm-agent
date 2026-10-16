// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { sendMessage, showI18nToast } = vi.hoisted(() => ({
  sendMessage: vi.fn<(input: string) => Promise<boolean>>(),
  showI18nToast: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({ default: { getState: () => ({ sendMessage }) } }));
vi.mock('@/services/i18nToastService', () => ({ showI18nToast }));

import { GoalHumanReviewAction } from '../GoalHumanReviewAction';

const t = ((key: string) => key) as unknown as Parameters<typeof GoalHumanReviewAction>[0]['t'];
const busyError = () => Object.assign(new Error('busy'), { name: 'AgentBusyError' });

function setup() {
  const onAction = vi.fn();
  render(<GoalHumanReviewAction onAction={onAction} t={t} />);
  return { onAction, input: screen.getByPlaceholderText('feedbackPlaceholder') as HTMLInputElement };
}

function type(input: HTMLInputElement, value: string): void {
  fireEvent.change(input, { target: { value } });
}

describe('GoalHumanReviewAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sendMessage.mockResolvedValue(true);
  });

  it('sends the typed feedback, then sends the goal back to work and empties the box', async () => {
    const { onAction, input } = setup();
    type(input, 'use the staging database');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(onAction).toHaveBeenCalledWith('reject'));
    expect(sendMessage).toHaveBeenCalledWith('use the staging database');
    expect(input).toHaveValue('');
  });

  it('falls back to the retries-reset message when the box is empty, from the button as well', async () => {
    const { onAction } = setup();

    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() => expect(onAction).toHaveBeenCalledWith('reject'));
    expect(sendMessage).toHaveBeenCalledWith('resetRetriesMessage');
  });

  it('keeps the goal in review and the text in the box when the message was not sent, so it can be edited and sent again', async () => {
    sendMessage.mockResolvedValueOnce(false);
    const { onAction, input } = setup();
    type(input, 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    await act(async () => undefined);
    expect(onAction).not.toHaveBeenCalled();
    expect(input).toHaveValue('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');
    expect(showI18nToast).not.toHaveBeenCalled();

    type(input, 'use the key from the vault');
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(onAction).toHaveBeenCalledWith('reject'));
    expect(sendMessage).toHaveBeenLastCalledWith('use the key from the vault');
  });

  it('tells the user the agent is busy and keeps both goal state and text when the server refuses the turn', async () => {
    sendMessage.mockRejectedValue(busyError());
    const { onAction, input } = setup();
    type(input, 'try again');

    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() =>
      expect(showI18nToast).toHaveBeenCalledWith(
        'chat.sendBlocked.title',
        undefined,
        expect.objectContaining({ descriptionKey: 'chat.sendBlocked.busyDescription' }),
      ),
    );
    expect(onAction).not.toHaveBeenCalled();
    expect(input).toHaveValue('try again');
  });

  it('reports any other failure with the generic notice and keeps the text', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    sendMessage.mockRejectedValue(new Error('boom'));
    const { onAction, input } = setup();
    type(input, 'try again');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() =>
      expect(showI18nToast).toHaveBeenCalledWith(
        'chat.messageFailed.title',
        undefined,
        expect.objectContaining({ descriptionKey: 'chat.messageFailed.generic' }),
      ),
    );
    expect(onAction).not.toHaveBeenCalled();
    expect(input).toHaveValue('try again');
    consoleError.mockRestore();
  });

  it('sends once however often it is submitted while the request is out', async () => {
    const { onAction, input } = setup();
    type(input, 'go on');

    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() => expect(onAction).toHaveBeenCalledTimes(1));
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it('keeps text typed while the request was out', async () => {
    let finish: (sent: boolean) => void = () => undefined;
    sendMessage.mockReturnValue(new Promise<boolean>((resolve) => (finish = resolve)));
    const { onAction, input } = setup();
    type(input, 'first');
    fireEvent.keyDown(input, { key: 'Enter' });

    type(input, 'first, and also this');
    finish(true);

    await waitFor(() => expect(onAction).toHaveBeenCalledWith('reject'));
    expect(input).toHaveValue('first, and also this');
  });

  it('ignores the Enter that confirms an input-method candidate', () => {
    const { onAction, input } = setup();
    type(input, 'ni hao');

    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });

    expect(sendMessage).not.toHaveBeenCalled();
    expect(onAction).not.toHaveBeenCalled();
  });

  it('approves without sending anything', () => {
    const { onAction } = setup();

    fireEvent.click(screen.getByRole('button', { name: 'forceApprove' }));

    expect(onAction).toHaveBeenCalledWith('approve');
    expect(sendMessage).not.toHaveBeenCalled();
  });
});
