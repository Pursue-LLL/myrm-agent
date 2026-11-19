/**
 * Skip and answer reach the request pipeline addressed to the pause that asked.
 *
 * Real scenario: the card announced for one pause is skipped. The resume request carries that pause's id, the only form
 * in which an empty answer is delivered to its pause instead of to no one. Runs the real card against the real store,
 * replacing only the request pipeline.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ClarificationForm, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import ClarificationInput from '../ClarificationInput';

const pipeline = vi.hoisted(() => ({ sendMessage: vi.fn<(...args: unknown[]) => Promise<boolean>>() }));

vi.mock('@/store/chat/messageRequest', () => pipeline);

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

const MESSAGE_ID = 'msg-1';
// Position of `resumeValue` in the arguments the store hands the request pipeline.
const RESUME_VALUE = 6;

const form: ClarificationForm = {
  title: 'Deployment',
  questions: [{ id: 'strategy', prompt: 'Choose a strategy', options: [{ id: 'blue-green', label: 'Blue green' }] }],
};

function openCard(interruptId?: string): void {
  const row: Message = {
    messageId: MESSAGE_ID,
    chatId: 'chat-1',
    createdAt: new Date(),
    content: '',
    role: 'assistant',
    clarification: { answered: false, form, ...(interruptId && { interruptId }) },
  };
  useChatStore.setState({ chatId: 'chat-1', messages: [row] });
  render(<ClarificationInput messageId={MESSAGE_ID} answered={false} form={form} />);
}

const sentResumeValue = () => pipeline.sendMessage.mock.calls[0]?.[RESUME_VALUE];

beforeEach(() => {
  pipeline.sendMessage.mockReset();
  pipeline.sendMessage.mockResolvedValue(true);
});

describe('ClarificationInput addressing', () => {
  it('sends a skip to the pause the card was announced for', async () => {
    openCard('int-1');

    fireEvent.click(screen.getByRole('button', { name: 'skip' }));

    await waitFor(() => expect(pipeline.sendMessage).toHaveBeenCalledTimes(1));
    expect(sentResumeValue()).toEqual({ interruptId: 'int-1' });
  });

  it('sends an answer to the pause the card was announced for', async () => {
    openCard('int-1');

    fireEvent.click(screen.getByRole('button', { name: /Blue green/ }));
    fireEvent.click(screen.getByRole('button', { name: 'submit' }));

    await waitFor(() => expect(pipeline.sendMessage).toHaveBeenCalledTimes(1));
    expect(sentResumeValue()).toEqual({ strategy: 'blue-green', interruptId: 'int-1' });
  });

  it('sends the bare answer for a card announced without an id', async () => {
    openCard();

    fireEvent.click(screen.getByRole('button', { name: 'skip' }));

    await waitFor(() => expect(pipeline.sendMessage).toHaveBeenCalledTimes(1));
    expect(sentResumeValue()).toEqual({});
  });
});
