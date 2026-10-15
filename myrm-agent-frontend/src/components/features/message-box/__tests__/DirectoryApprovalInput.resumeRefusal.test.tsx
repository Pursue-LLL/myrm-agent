/**
 * A refused resume must neither mark the directory card answered nor show the folder as granted; a dispatched one must
 * release the composer the card took over, except for a further request the resumed run raised on the same row.
 *
 * Real scenario: the user presses grant after the session expired. The resume request is refused, so the server never
 * received the grant; the optimistic access-root refresh would still list the folder as accessible and the card would
 * read as handled while the agent stays blocked. Runs the real card against the real store, replacing only the
 * request pipeline and the access-root refresh.
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

    await waitFor(() => expect(isAnswered()).toBe(true));
    expect(refreshSessionAccessRoots).toHaveBeenCalledWith('chat-1', {
      optimistic: { path: '/data/reports', writable: true, source: 'hitl_grant' },
    });
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

    await waitFor(() => expect(isAnswered()).toBe(true));
    expect(toast.warning).toHaveBeenCalledWith('expired');
    expect(toast.error).not.toHaveBeenCalled();
    expect(refreshSessionAccessRoots).not.toHaveBeenCalled();
    expect(findActivePendingDirectoryRequest(useChatStore.getState().messages)).toBeNull();
  });
});
