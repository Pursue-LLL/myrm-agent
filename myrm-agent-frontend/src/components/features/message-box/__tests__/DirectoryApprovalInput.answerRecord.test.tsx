/**
 * A directory card keeps how it was settled, so the transcript says which folder was granted, that access was denied,
 * or that nobody answered in time, and a refused resume gives the user back the folder they typed.
 *
 * Real scenarios: the user grants a report folder with write access and reopens the chat later (the card names the
 * folder); the user is away and the timeout declines the request (the card says nobody answered); the resume request is
 * refused after the user picked a folder, which closed the composer-takeover card (the folder must be there when the
 * card comes back). Runs the real card against the real store, replacing only the request pipeline and the
 * access-root refresh.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApprovalExpiredError } from '@/store/chat/streamErrors';
import type { HitlAnswerRecord, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import DirectoryApprovalInput from '../DirectoryApprovalInput';
import { deferred } from './hitlCardTestKit';

const pipeline = vi.hoisted(() => ({ sendMessage: vi.fn<() => Promise<boolean>>() }));

vi.mock('@/store/chat/messageRequest', () => pipeline);

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: () => false,
}));

vi.mock('@/lib/sessionAccessRefresh', () => ({
  refreshSessionAccessRoots: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../DirectoryBrowsePopover', () => ({
  default: () => null,
  rememberDirectoryGrantPath: vi.fn(),
}));

const MESSAGE_ID = 'msg-1';
const REQUEST = { path: '/data/reports', writable: true };

const pendingDirectory: Message = {
  messageId: MESSAGE_ID,
  chatId: 'chat-1',
  createdAt: new Date(),
  content: '',
  role: 'assistant',
  directoryRequest: { answered: false, request: REQUEST },
};

const card = () => useChatStore.getState().messages[0]?.directoryRequest;

const renderCard = () => render(<DirectoryApprovalInput messageId={MESSAGE_ID} answered={false} request={REQUEST} />);

const renderSettled = (answerRecord: HitlAnswerRecord | undefined) =>
  render(<DirectoryApprovalInput messageId={MESSAGE_ID} answered request={REQUEST} answerRecord={answerRecord} />);

beforeEach(() => {
  pipeline.sendMessage.mockReset();
  useChatStore.setState({ chatId: 'chat-1', messages: [structuredClone(pendingDirectory)] });
});

describe('answer record written when the card closes', () => {
  it('keeps the granted folder and its write access as the user answer', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'grant' }));

    await waitFor(() =>
      expect(card()?.answerRecord).toEqual({
        by: 'user',
        value: { granted: true, path: '/data/reports', writable: true },
      }),
    );
  });

  it('keeps the denial as the user answer', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'deny' }));

    await waitFor(() => expect(card()?.answerRecord).toEqual({ by: 'user', value: { granted: false } }));
  });

  it('keeps no record on a card the refused resume put back', async () => {
    pipeline.sendMessage.mockResolvedValue(false);

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'grant' }));

    await waitFor(() => expect(card()?.answered).toBe(false));
    expect(card()?.answerRecord).toBeUndefined();
  });

  it('records that the timeout declined the request when the grant arrived too late', async () => {
    pipeline.sendMessage.mockRejectedValue(new ApprovalExpiredError());

    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'grant' }));

    await waitFor(() => expect(card()?.answerRecord).toEqual({ by: 'timeout', value: { granted: false } }));
    expect(card()?.answered).toBe(true);
  });
});

describe('settled card', () => {
  it('names the folder that was granted with write access', () => {
    renderSettled({ by: 'user', value: { granted: true, path: '/data/reports', writable: true } });

    expect(screen.getByText('grantedWritable')).toBeInTheDocument();
    expect(screen.getByText('/data/reports')).toBeInTheDocument();
  });

  it('names the folder that was granted read-only', () => {
    renderSettled({ by: 'user', value: { granted: true, path: '/data/reports', writable: false } });

    expect(screen.getByText('grantedReadOnly')).toBeInTheDocument();
    expect(screen.getByText('/data/reports')).toBeInTheDocument();
  });

  it('says access was denied', () => {
    renderSettled({ by: 'user', value: { granted: false } });

    expect(screen.getByText('denied')).toBeInTheDocument();
    expect(screen.queryByText('answered')).not.toBeInTheDocument();
  });

  it('says nobody answered in time', () => {
    renderSettled({ by: 'timeout', value: { granted: false } });

    expect(screen.getByText('timedOut')).toBeInTheDocument();
    expect(screen.queryByText('answered')).not.toBeInTheDocument();
  });

  it.each([
    ['a card settled before records existed', undefined],
    ['a record that is not a directory decision', { by: 'user', value: 'granted' } as HitlAnswerRecord],
  ])('falls back to the plain answered label for %s', (_label, answerRecord) => {
    renderSettled(answerRecord);

    expect(screen.getByText('answered')).toBeInTheDocument();
  });
});

describe('draft kept across the card closing', () => {
  const pathInput = () => screen.getByPlaceholderText('pathPlaceholder');

  const editAndGrant = () => {
    fireEvent.change(pathInput(), { target: { value: '/data/exports' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'grant' }));
  };

  it('restores the folder and write access when the card comes back after a refused resume', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    const first = renderCard();
    editAndGrant();
    await waitFor(() => expect(card()?.answered).toBe(true));
    // The composer takeover ends while the request is in flight, which unmounts the card.
    first.unmount();
    run.resolve(false);
    await waitFor(() => expect(card()?.answered).toBe(false));

    renderCard();

    expect(pathInput()).toHaveValue('/data/exports');
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('starts from the request again once the resumed run took the answer', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    const first = renderCard();
    editAndGrant();
    await waitFor(() => expect(card()?.answerRecord).toBeDefined());
    first.unmount();
    useChatStore.setState((state) => {
      state.messages[0].directoryRequest = { answered: false, request: REQUEST };
    });

    renderCard();

    expect(pathInput()).toHaveValue('/data/reports');
    expect(screen.getByRole('checkbox')).toBeChecked();
  });

  it('starts from the request again once the timeout had already declined it', async () => {
    pipeline.sendMessage.mockRejectedValue(new ApprovalExpiredError());

    const first = renderCard();
    editAndGrant();
    await waitFor(() => expect(card()?.answerRecord).toBeDefined());
    first.unmount();
    useChatStore.setState((state) => {
      state.messages[0].directoryRequest = { answered: false, request: REQUEST };
    });

    renderCard();

    expect(pathInput()).toHaveValue('/data/reports');
  });
});
