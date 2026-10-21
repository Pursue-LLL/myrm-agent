/**
 * A clarification card keeps how it was settled, so the transcript tells an answer from a skip from a timeout, and a
 * refused resume gives the user back what they typed.
 *
 * Real scenarios: the user answers a deployment question and reopens the chat later (the card shows their choice, not a
 * bare "answered"); the user is away and the 15-minute timeout continues the turn (the card says nobody answered);
 * the user answers on the laptop after the phone already did, or after the timeout fired (the server refuses the
 * second resume and cannot say which of the two happened, so the card only says it was already handled); the resume
 * request is refused after the user wrote a long answer, which closed the composer-takeover card (the answer must be
 * there when the card comes back). Runs the real card against the real store, replacing only the request pipeline.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { submitClarifyResponse } from '@/services/chat';
import { ApprovalAlreadyResolvedError } from '@/store/chat/streamErrors';
import type { ClarificationForm, HitlAnswerRecord, Message } from '@/store/chat/types';
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

const record = () => useChatStore.getState().messages[0]?.clarification?.answerRecord;

const renderCard = (isResumeMode = true) =>
  render(<ClarificationInput messageId={MESSAGE_ID} answered={false} form={form} isResumeMode={isResumeMode} />);

const renderSettled = (answerRecord: HitlAnswerRecord | undefined) =>
  render(<ClarificationInput messageId={MESSAGE_ID} answered form={form} isResumeMode answerRecord={answerRecord} />);

beforeEach(() => {
  pipeline.sendMessage.mockReset();
  vi.mocked(submitClarifyResponse).mockReset();
  useChatStore.setState({ chatId: 'chat-1', messages: [structuredClone(pendingClarification)] });
});

describe('answer record written when the card closes', () => {
  it('keeps the skip as the user answer once the resume is dispatched', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'skip' }));

    await waitFor(() => expect(record()).toEqual({ by: 'user', value: {} }));
  });

  it('keeps the chosen option id under its question id', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /Blue green/ }));
    fireEvent.click(screen.getByRole('button', { name: 'submit' }));

    await waitFor(() => expect(record()).toEqual({ by: 'user', value: { strategy: 'blue-green' } }));
  });

  it('keeps no record on a card the refused resume put back', async () => {
    pipeline.sendMessage.mockResolvedValue(false);

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'skip' }));

    await waitFor(() => expect(useChatStore.getState().messages[0]?.clarification?.answered).toBe(false));
    expect(record()).toBeUndefined();
  });

  it('records that the card was already handled, not by whom, when the answer arrived too late', async () => {
    pipeline.sendMessage.mockRejectedValue(new ApprovalAlreadyResolvedError());

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'skip' }));

    await waitFor(() => expect(record()).toEqual({ by: 'already_handled', value: null }));
    expect(useChatStore.getState().messages[0]?.clarification?.answered).toBe(true);
  });

  it('leaves a card the resumed run replaced alone when the answer then turns out to be already handled', async () => {
    pipeline.sendMessage.mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].clarification = { answered: false, isResumeMode: true, form };
      });
      throw new ApprovalAlreadyResolvedError();
    });

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'skip' }));

    await waitFor(() => expect(pipeline.sendMessage).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: 'skip' })).toBeEnabled());
    expect(record()).toBeUndefined();
    expect(useChatStore.getState().messages[0]?.clarification?.answered).toBe(false);
  });

  it('keeps a legacy clarify answer as the user answer once the server accepted it', async () => {
    vi.mocked(submitClarifyResponse).mockResolvedValue(undefined);

    renderCard(false);
    fireEvent.click(screen.getByRole('button', { name: 'skip' }));

    await waitFor(() => expect(record()).toEqual({ by: 'user', value: '' }));
  });
});

describe('settled card', () => {
  it('shows the question and the option label the user chose', () => {
    renderSettled({ by: 'user', value: { strategy: 'blue-green' } });

    expect(screen.getByText('answered')).toBeInTheDocument();
    expect(screen.getByText('Choose a strategy')).toBeInTheDocument();
    expect(screen.getByText('Blue green')).toBeInTheDocument();
  });

  it('says the user skipped', () => {
    renderSettled({ by: 'user', value: {} });

    expect(screen.getByText('answeredSkipped')).toBeInTheDocument();
    expect(screen.queryByText('answered')).not.toBeInTheDocument();
  });

  it('says nobody answered in time', () => {
    renderSettled({ by: 'timeout', value: {} });

    expect(screen.getByText('answeredTimeout')).toBeInTheDocument();
    expect(screen.queryByText('answered')).not.toBeInTheDocument();
  });

  it('says it was already handled without naming who handled it', () => {
    renderSettled({ by: 'already_handled', value: null });

    expect(screen.getByText('answeredHandled')).toBeInTheDocument();
    expect(screen.queryByText('answeredTimeout')).not.toBeInTheDocument();
    expect(screen.queryByText('answered')).not.toBeInTheDocument();
  });

  it.each([
    ['a card settled before records existed', undefined],
    ['a record for questions this form never asked', { by: 'user', value: { unrelated: 'x' } } as HitlAnswerRecord],
  ])('falls back to the plain answered label for %s', (_label, answerRecord) => {
    renderSettled(answerRecord);

    expect(screen.getByText('answered')).toBeInTheDocument();
    expect(screen.queryByText('Choose a strategy')).not.toBeInTheDocument();
  });
});

describe('a card that asked for sign-off', () => {
  const signOffForm: ClarificationForm = { ...form, requiresConfirmation: true };
  const renderSignOff = (answerRecord: HitlAnswerRecord) =>
    render(
      <ClarificationInput
        messageId={MESSAGE_ID}
        answered
        form={signOffForm}
        isResumeMode
        answerRecord={answerRecord}
      />,
    );

  it('says the action was not approved when the user skipped it', () => {
    renderSignOff({ by: 'user', value: {} });

    expect(screen.getByText('answeredSkippedUnconfirmed')).toBeInTheDocument();
    expect(screen.queryByText('answeredSkipped')).not.toBeInTheDocument();
  });

  it('says the action was not approved when nobody answered in time', () => {
    renderSignOff({ by: 'timeout', value: {} });

    expect(screen.getByText('answeredTimeoutUnconfirmed')).toBeInTheDocument();
    expect(screen.queryByText('answeredTimeout')).not.toBeInTheDocument();
  });

  it('does not say the action was approved or rejected when another client already handled it', () => {
    renderSignOff({ by: 'already_handled', value: null });

    expect(screen.getByText('answeredHandledSignOff')).toBeInTheDocument();
    expect(screen.queryByText('answeredHandled')).not.toBeInTheDocument();
    expect(screen.queryByText('answeredTimeoutUnconfirmed')).not.toBeInTheDocument();
  });

  it('still shows what the user chose when they did answer', () => {
    renderSignOff({ by: 'user', value: { strategy: ['blue-green'] } });

    expect(screen.getByText('Blue green')).toBeInTheDocument();
    expect(screen.queryByText('answeredSkippedUnconfirmed')).not.toBeInTheDocument();
  });
});

describe('draft kept across the card closing', () => {
  const typeAnswer = () => {
    fireEvent.change(screen.getByPlaceholderText('freeTextWithOptionsPlaceholder'), {
      target: { value: 'ship it on Friday' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'submit' }));
  };

  it('restores what was typed when the card comes back after a refused resume', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    const first = renderCard();
    typeAnswer();
    await waitFor(() => expect(useChatStore.getState().messages[0]?.clarification?.answered).toBe(true));
    // The composer takeover ends while the request is in flight, which unmounts the card.
    first.unmount();
    run.resolve(false);
    await waitFor(() => expect(useChatStore.getState().messages[0]?.clarification?.answered).toBe(false));

    renderCard();

    expect(screen.getByPlaceholderText('freeTextWithOptionsPlaceholder')).toHaveValue('ship it on Friday');
  });

  it('restores the chosen option as well', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    const first = renderCard();
    fireEvent.click(screen.getByRole('button', { name: /Blue green/ }));
    fireEvent.click(screen.getByRole('button', { name: 'submit' }));
    await waitFor(() => expect(useChatStore.getState().messages[0]?.clarification?.answered).toBe(true));
    first.unmount();
    run.resolve(false);
    await waitFor(() => expect(useChatStore.getState().messages[0]?.clarification?.answered).toBe(false));

    renderCard();

    expect(screen.getByRole('button', { name: 'submit' })).toBeEnabled();
  });

  it('starts empty once the resumed run took the answer', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    const first = renderCard();
    typeAnswer();
    await waitFor(() => expect(record()).toBeDefined());
    first.unmount();
    useChatStore.setState((state) => {
      state.messages[0].clarification = { answered: false, isResumeMode: true, form };
    });

    renderCard();

    expect(screen.getByPlaceholderText('freeTextWithOptionsPlaceholder')).toHaveValue('');
  });

  it('starts empty when the resumed run raises another question while its request is still open', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    const first = renderCard();
    typeAnswer();
    await waitFor(() => expect(record()).toBeDefined());
    first.unmount();
    useChatStore.setState((state) => {
      state.messages[0].clarification = { answered: false, isResumeMode: true, form };
    });

    renderCard();

    expect(screen.getByPlaceholderText('freeTextWithOptionsPlaceholder')).toHaveValue('');
    run.resolve(true);
  });

  it('starts empty once someone else had already continued the turn', async () => {
    pipeline.sendMessage.mockRejectedValue(new ApprovalAlreadyResolvedError());

    const first = renderCard();
    typeAnswer();
    await waitFor(() => expect(record()).toBeDefined());
    first.unmount();
    useChatStore.setState((state) => {
      state.messages[0].clarification = { answered: false, isResumeMode: true, form };
    });

    renderCard();

    expect(screen.getByPlaceholderText('freeTextWithOptionsPlaceholder')).toHaveValue('');
  });
});
