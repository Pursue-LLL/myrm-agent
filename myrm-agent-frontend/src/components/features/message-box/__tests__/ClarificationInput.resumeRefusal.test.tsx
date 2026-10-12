/**
 * A refused resume must leave the clarification card answerable.
 *
 * Real scenario: the user returns to a pending clarification after the session expired and presses skip. The resume
 * request is refused, so the agent never continues; marking the card answered would leave the user waiting for a
 * turn that does not exist. Runs the real card against the real store, replacing only the request pipeline.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ClarificationForm, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import ClarificationInput from '../ClarificationInput';

const pipeline = vi.hoisted(() => ({ sendMessage: vi.fn<() => Promise<boolean>>() }));

vi.mock('@/store/chat/messageRequest', () => pipeline);

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
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

function skipClarification(): void {
  render(<ClarificationInput messageId={MESSAGE_ID} answered={false} form={form} isResumeMode />);
  fireEvent.click(screen.getByRole('button', { name: 'skip' }));
}

beforeEach(() => {
  pipeline.sendMessage.mockReset();
  vi.mocked(toast.error).mockClear();
  useChatStore.setState({ chatId: 'chat-1', messages: [structuredClone(pendingClarification)] });
});

describe('ClarificationInput resume', () => {
  it('keeps the card open and reports the failure when the resume is refused', async () => {
    pipeline.sendMessage.mockResolvedValue(false);

    skipClarification();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('submitFailed'));
    expect(isAnswered()).toBe(false);
  });

  it('marks the card answered once the resume is dispatched', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    skipClarification();

    await waitFor(() => expect(isAnswered()).toBe(true));
    expect(toast.error).not.toHaveBeenCalled();
  });
});
