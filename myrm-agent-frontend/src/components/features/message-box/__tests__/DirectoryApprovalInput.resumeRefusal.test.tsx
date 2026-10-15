/**
 * The directory card closes the moment it is answered, releasing the composer it took over, and reopens only if the
 * server never took the answer; a refused resume must also not show the folder as granted.
 *
 * Real scenario: the user presses grant. The resume request streams the whole resumed run, and until the card's row says
 * answered the card keeps the composer, hiding Stop, steer and queue. When the session had expired the resume is
 * refused: the server never received the grant, so the card must come back and the access-root refresh must not list
 * the folder. Runs the real card against the real store, replacing only the request pipeline and the access-root
 * refresh.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { refreshSessionAccessRoots } from '@/lib/sessionAccessRefresh';
import { findActivePendingDirectoryRequest } from '@/store/chat/directoryRequestState';
import { ApprovalExpiredError } from '@/store/chat/streamErrors';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import DirectoryApprovalInput from '../DirectoryApprovalInput';

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

const pendingDirectory: Message = {
  messageId: MESSAGE_ID,
  chatId: 'chat-1',
  createdAt: new Date(),
  content: '',
  role: 'assistant',
  directoryRequest: { answered: false, isResumeMode: true, request: { path: '/data/reports', writable: true } },
};

const isAnswered = () => useChatStore.getState().messages[0]?.directoryRequest?.answered;

/** A request that stays in flight until the test settles it, like a resumed run that is still streaming. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** Rendered with the props MessageBox and MessageInput pass: the card closes itself through the store. */
function grantDirectory(): void {
  render(
    <DirectoryApprovalInput
      messageId={MESSAGE_ID}
      answered={false}
      isResumeMode
      request={{ path: '/data/reports', writable: true }}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'grant' }));
}

beforeEach(() => {
  pipeline.sendMessage.mockReset();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.warning).mockClear();
  vi.mocked(refreshSessionAccessRoots).mockClear();
  useChatStore.setState({ chatId: 'chat-1', messages: [structuredClone(pendingDirectory)] });
});

describe('DirectoryApprovalInput resume', () => {
  it('reports the failure and records no grant when the resume is refused', async () => {
    pipeline.sendMessage.mockResolvedValue(false);

    grantDirectory();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('submitFailed'));
    expect(refreshSessionAccessRoots).not.toHaveBeenCalled();
    expect(isAnswered()).toBe(false);
  });

  it('records the grant and releases the composer once the resumed run has streamed into the row', async () => {
    pipeline.sendMessage.mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].content = 'continuing with the folder';
      });
      return true;
    });

    grantDirectory();

    await waitFor(() =>
      expect(refreshSessionAccessRoots).toHaveBeenCalledWith('chat-1', {
        optimistic: { path: '/data/reports', writable: true, source: 'hitl_grant' },
      }),
    );
    expect(isAnswered()).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
    expect(findActivePendingDirectoryRequest(useChatStore.getState().messages)).toBeNull();
  });

  it('leaves a second request the resumed run raised on the same row open', async () => {
    pipeline.sendMessage.mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].directoryRequest = {
          answered: false,
          isResumeMode: true,
          request: { path: '/data/exports', writable: false },
        };
      });
      return true;
    });

    grantDirectory();

    await waitFor(() => expect(screen.getByRole('button', { name: 'grant' })).toBeEnabled());
    expect(refreshSessionAccessRoots).toHaveBeenCalledTimes(1);
    expect(findActivePendingDirectoryRequest(useChatStore.getState().messages)?.directoryRequest.request?.path).toBe(
      '/data/exports',
    );
  });

  it('closes the card without recording a grant when the timeout already declined the request', async () => {
    pipeline.sendMessage.mockRejectedValue(new ApprovalExpiredError());

    grantDirectory();

    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith('expired'));
    expect(isAnswered()).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
    expect(refreshSessionAccessRoots).not.toHaveBeenCalled();
    expect(findActivePendingDirectoryRequest(useChatStore.getState().messages)).toBeNull();
  });

  it('releases the composer takeover while the resumed run is still streaming', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    grantDirectory();

    await waitFor(() => expect(isAnswered()).toBe(true));
    expect(findActivePendingDirectoryRequest(useChatStore.getState().messages)).toBeNull();
    expect(refreshSessionAccessRoots).not.toHaveBeenCalled();
    run.resolve(true);
  });

  it('puts the card back when the resume turns out not to be delivered', async () => {
    const run = deferred<boolean>();
    pipeline.sendMessage.mockReturnValue(run.promise);

    grantDirectory();
    await waitFor(() => expect(isAnswered()).toBe(true));
    run.resolve(false);

    await waitFor(() => expect(isAnswered()).toBe(false));
    expect(toast.error).toHaveBeenCalledWith('submitFailed');
    expect(refreshSessionAccessRoots).not.toHaveBeenCalled();
    expect(findActivePendingDirectoryRequest(useChatStore.getState().messages)?.messageId).toBe(MESSAGE_ID);
  });

  it('does not reopen a request the resumed run already settled when the connection then drops', async () => {
    pipeline.sendMessage.mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].directoryRequest = {
          answered: true,
          isResumeMode: true,
          request: { path: '/data/exports', writable: false },
        };
      });
      throw new Error('stream dropped');
    });

    grantDirectory();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('submitFailed'));
    expect(isAnswered()).toBe(true);
  });
});
