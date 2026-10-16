// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { readSendOrigin, sendGoalReviewFeedback } = vi.hoisted(() => ({
  readSendOrigin: vi.fn(),
  sendGoalReviewFeedback: vi.fn<(origin: unknown, feedback: string) => Promise<void>>(),
}));

vi.mock('@/components/features/message-box/userMessageResend', () => ({ readSendOrigin, sendGoalReviewFeedback }));

import { GoalHumanReviewAction } from '../GoalHumanReviewAction';

const t = ((key: string) => key) as unknown as Parameters<typeof GoalHumanReviewAction>[0]['t'];
const reviewChat = { chatId: 'chat-under-review', agentId: 'agent-1', incognito: false };

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
    readSendOrigin.mockReturnValue(reviewChat);
    sendGoalReviewFeedback.mockResolvedValue(undefined);
  });

  it('sends the goal back to work with the feedback, then hands the feedback to the chat send and empties the box', async () => {
    const { onAction, input } = setup();
    type(input, 'use the staging database');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(sendGoalReviewFeedback).toHaveBeenCalledWith(reviewChat, 'use the staging database'));
    expect(onAction).toHaveBeenCalledWith('reject', 'use the staging database');
    expect(input).toHaveValue('');
    // The agent reads only an active goal: the goal is back at work before the feedback turn starts.
    expect(onAction.mock.invocationCallOrder[0]).toBeLessThan(sendGoalReviewFeedback.mock.invocationCallOrder[0]);
  });

  it('uses the retries-reset message when the box is empty, from the button as well', async () => {
    const { onAction } = setup();

    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() => expect(sendGoalReviewFeedback).toHaveBeenCalledWith(reviewChat, 'resetRetriesMessage'));
    expect(onAction).toHaveBeenCalledWith('reject', 'resetRetriesMessage');
  });

  it('keeps the text in the box and sends nothing when the server did not take the reject, so it can be edited', async () => {
    const { onAction, input } = setup();
    onAction.mockResolvedValueOnce(false);
    type(input, 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(onAction).toHaveBeenCalledTimes(1));
    await flush();

    expect(sendGoalReviewFeedback).not.toHaveBeenCalled();
    expect(input).toHaveValue('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    type(input, 'use the key from the vault');
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(sendGoalReviewFeedback).toHaveBeenCalledWith(reviewChat, 'use the key from the vault'));
  });

  it('reads the chat of the review before the request goes out, so a chat opened meanwhile does not take the feedback', async () => {
    const { onAction, input } = setup();
    const anotherChat = { chatId: 'chat-opened-meanwhile', agentId: 'agent-2', incognito: false };
    readSendOrigin.mockReturnValueOnce(reviewChat).mockReturnValue(anotherChat);
    type(input, 'try the other branch');

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(sendGoalReviewFeedback).toHaveBeenCalledWith(reviewChat, 'try the other branch'));
    expect(readSendOrigin).toHaveBeenCalledTimes(1);
    expect(readSendOrigin.mock.invocationCallOrder[0]).toBeLessThan(onAction.mock.invocationCallOrder[0]);
  });

  it('does not wait for the turn the feedback starts', async () => {
    sendGoalReviewFeedback.mockReturnValue(new Promise<void>(() => undefined));
    const { onAction, input } = setup();
    type(input, 'first');
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(sendGoalReviewFeedback).toHaveBeenCalledTimes(1));

    type(input, 'second');
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(onAction).toHaveBeenCalledTimes(2));
  });

  it('rejects once however often it is submitted while the request is out', async () => {
    const { onAction, input } = setup();
    type(input, 'go on');

    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'rejectAndRetry' }));

    await waitFor(() => expect(sendGoalReviewFeedback).toHaveBeenCalledTimes(1));
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

    await waitFor(() => expect(sendGoalReviewFeedback).toHaveBeenCalledWith(reviewChat, 'first'));
    expect(input).toHaveValue('first, and also this');
  });

  it('ignores the Enter that confirms an input-method candidate', () => {
    const { onAction, input } = setup();
    type(input, 'ni hao');

    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });

    expect(onAction).not.toHaveBeenCalled();
    expect(sendGoalReviewFeedback).not.toHaveBeenCalled();
  });

  it('approves without sending anything', () => {
    const { onAction } = setup();

    fireEvent.click(screen.getByRole('button', { name: 'forceApprove' }));

    expect(onAction).toHaveBeenCalledWith('approve');
    expect(sendGoalReviewFeedback).not.toHaveBeenCalled();
  });
});
