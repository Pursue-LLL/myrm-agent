/**
 * The clarification card closes the moment it is answered and reopens only if the server never took the answer.
 *
 * Real scenario: the user presses skip. The resume request streams the whole resumed run, and until the card's row says
 * answered the card keeps the composer, hiding Stop, steer and queue. A refused resume (session expired) must put the
 * card back, because the agent never continues. Runs the real card against the real store, replacing only the request
 * pipeline.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { submitClarifyResponse } from '@/services/chat';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import { ApprovalExpiredError } from '@/store/chat/streamErrors';
import type { ClarificationForm, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import ClarificationInput from '../ClarificationInput';
import { deferred } from './hitlCardTestKit';

const pipeline = vi.hoisted(() => ({ sendMessage: vi.fn<() => Promise<boolean>>() }));

vi.mock('@/store/chat/messageRequest', () => pipeline);

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/services/chat', () => ({
  submitClarifyResponse: vi.fn(),
}));

const MESSAGE_ID = 'msg-1';

const form: ClarificationForm = {
  title: 'Deployment',
  questions: [{ id: 'strategy', prompt: 'Choose a strategy', options: [{ id: 'blue-green', label: 'Blue green' }] }],
};

const pendingClarification: Message = {
  messageId: MESSAGE_ID,
  chatId: 'chat-1',
  createdAt: new Date(),
  content: '',
  role: 'assistant',
  clarification: { answered: false, isResumeMode: true, form },
};

const isAnswered = () => useChatStore.getState().messages[0]?.clarification?.answered;

function skipClarification(isResumeMode = true): void {
  render(<ClarificationInput messageId={MESSAGE_ID} answered={false} form={form} isResumeMode={isResumeMode} />);
  fireEvent.click(screen.getByRole('button', { name: 'skip' }));
}

const secondForm: ClarificationForm = {
  title: 'Rollout',
  questions: [{ id: 'region', prompt: 'Choose a region', options: [{ id: 'eu', label: 'Europe' }] }],
};

beforeEach(() => {
  pipeline.sendMessage.mockReset();
  vi.mocked(submitClarifyResponse).mockReset();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.warning).mockClear();
  useChatStore.setState({ chatId: 'chat-1', messages: [structuredClone(pendingClarification)] });
});

describe('ClarificationInput resume', () => {
  it('keeps the card open and reports the failure when the resume is refused', async () => {
    pipeline.sendMessage.mockResolvedValue(false);

    skipClarification();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('submitFailed'));
    expect(isAnswered()).toBe(false);
  });

  it('keeps the card answered once the resume is dispatched', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    skipClarification();

    await waitFor(() => expect(screen.getByRole('button', { name: 'skip' })).toBeEnabled());
    expect(isAnswered()).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('closes the card and says the wait ran out when the timeout already continued the turn', async () => {
    pipeline.sendMessage.mockRejectedValue(new ApprovalExpiredError());

    skipClarification();

    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith('expired'));
    expect(isAnswered()).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
  });

  describe('when the timeout got there first', () => {
    const answerWithBlueGreen = () => {
      render(<ClarificationInput messageId={MESSAGE_ID} answered={false} form={form} isResumeMode />);
      fireEvent.click(screen.getByRole('button', { name: /Blue green/ }));
      fireEvent.click(screen.getByRole('button', { name: 'submit' }));
    };

    beforeEach(() => {
      pipeline.sendMessage.mockRejectedValue(new ApprovalExpiredError());
      useChatStore.setState({ inputMessage: '' });
    });

    it('hands the late answer to the composer so it can still be sent', async () => {
      answerWithBlueGreen();

      await waitFor(() => expect(toast.warning).toHaveBeenCalledWith('expired'));
      expect(useChatStore.getState().inputMessage).toBe('Choose a strategy: Blue green');
    });

    it('keeps what the user had already typed in the composer', async () => {
      useChatStore.setState({ inputMessage: 'and one more thing  ' });

      answerWithBlueGreen();

      await waitFor(() => expect(toast.warning).toHaveBeenCalledWith('expired'));
      expect(useChatStore.getState().inputMessage).toBe('and one more thing\n\nChoose a strategy: Blue green');
    });

    it('hands nothing back for a skip', async () => {
      skipClarification();

      await waitFor(() => expect(toast.warning).toHaveBeenCalledWith('expired'));
      expect(useChatStore.getState().inputMessage).toBe('');
    });
  });

  it('releases the composer takeover while the resumed run is still streaming', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    skipClarification();

    await waitFor(() => expect(isAnswered()).toBe(true));
    expect(findActivePendingClarification(useChatStore.getState().messages)).toBeNull();
    run.resolve(true);
  });

  it('puts the card back when the resume turns out not to be delivered', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    skipClarification();
    await waitFor(() => expect(isAnswered()).toBe(true));
    run.resolve(false);

    await waitFor(() => expect(isAnswered()).toBe(false));
    expect(toast.error).toHaveBeenCalledWith('submitFailed');
    expect(findActivePendingClarification(useChatStore.getState().messages)?.messageId).toBe(MESSAGE_ID);
  });

  it('leaves a second clarification the resumed run raised on the same row open', async () => {
    pipeline.sendMessage.mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].clarification = { answered: false, isResumeMode: true, form: secondForm };
      });
      return true;
    });

    skipClarification();

    await waitFor(() => expect(screen.getByRole('button', { name: 'skip' })).toBeEnabled());
    expect(findActivePendingClarification(useChatStore.getState().messages)?.clarification.form?.title).toBe('Rollout');
  });

  it('does not reopen a card the resumed run already settled when the connection then drops', async () => {
    pipeline.sendMessage.mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].clarification = { answered: true, isResumeMode: true, form: secondForm };
      });
      throw new Error('stream dropped');
    });

    skipClarification();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('submitFailed'));
    expect(isAnswered()).toBe(true);
  });

  it('closes a legacy clarify answer only after the server accepted it', async () => {
    const accepted = deferred<void>();
    vi.mocked(submitClarifyResponse).mockReturnValue(accepted.promise);

    skipClarification(false);

    await waitFor(() => expect(submitClarifyResponse).toHaveBeenCalledWith(MESSAGE_ID, ''));
    expect(isAnswered()).toBe(false);
    accepted.resolve();

    await waitFor(() => expect(isAnswered()).toBe(true));
    expect(pipeline.sendMessage).not.toHaveBeenCalled();
  });
});
