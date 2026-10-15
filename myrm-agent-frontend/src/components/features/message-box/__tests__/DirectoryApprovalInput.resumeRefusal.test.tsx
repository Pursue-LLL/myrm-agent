/**
 * A refused resume must neither mark the directory card answered nor show the folder as granted.
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
import { ApprovalExpiredError } from '@/store/chat/streamErrors';
import useChatStore from '@/store/useChatStore';

import DirectoryApprovalInput from '../DirectoryApprovalInput';

const pipeline = vi.hoisted(() => ({ sendMessage: vi.fn<() => Promise<boolean>>() }));
const transcript = vi.hoisted(() => ({ refreshOpenChatTranscript: vi.fn<(chatId: string) => Promise<void>>() }));

vi.mock('@/store/chat/messageRequest', () => pipeline);

vi.mock('@/store/chat/chatTranscriptRefresh', () => transcript);

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

const onAnswered = vi.fn();

function grantDirectory(): void {
  render(
    <DirectoryApprovalInput
      messageId="msg-1"
      answered={false}
      request={{ path: '/data/reports', writable: true }}
      onAnswered={onAnswered}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'grant' }));
}

beforeEach(() => {
  pipeline.sendMessage.mockReset();
  transcript.refreshOpenChatTranscript.mockReset();
  onAnswered.mockClear();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.warning).mockClear();
  vi.mocked(refreshSessionAccessRoots).mockClear();
  useChatStore.setState({ chatId: 'chat-1' });
});

describe('DirectoryApprovalInput resume', () => {
  it('reports the failure and records no grant when the resume is refused', async () => {
    pipeline.sendMessage.mockResolvedValue(false);

    grantDirectory();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('submitFailed'));
    expect(refreshSessionAccessRoots).not.toHaveBeenCalled();
    expect(onAnswered).not.toHaveBeenCalled();
    expect(transcript.refreshOpenChatTranscript).not.toHaveBeenCalled();
  });

  it('records the grant and marks the card answered once the resume is dispatched', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    grantDirectory();

    await waitFor(() => expect(onAnswered).toHaveBeenCalledTimes(1));
    expect(refreshSessionAccessRoots).toHaveBeenCalledWith('chat-1', {
      optimistic: { path: '/data/reports', writable: true, source: 'hitl_grant' },
    });
    expect(toast.error).not.toHaveBeenCalled();
    expect(transcript.refreshOpenChatTranscript).not.toHaveBeenCalled();
  });

  it('closes the card without recording a grant and pulls in what the timeout continued with', async () => {
    pipeline.sendMessage.mockRejectedValue(new ApprovalExpiredError());
    transcript.refreshOpenChatTranscript.mockResolvedValue();

    grantDirectory();

    // Closed once right away and once more after the stored row replaced the message.
    await waitFor(() => expect(onAnswered).toHaveBeenCalledTimes(2));
    expect(toast.warning).toHaveBeenCalledWith('expired');
    expect(toast.error).not.toHaveBeenCalled();
    expect(refreshSessionAccessRoots).not.toHaveBeenCalled();
    expect(transcript.refreshOpenChatTranscript).toHaveBeenCalledWith('chat-1');
  });
});
