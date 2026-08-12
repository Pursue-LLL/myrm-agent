/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { RewindDialog } from '../RewindDialog';

const { toastMock, rewindToMessageMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  rewindToMessageMock: vi.fn(),
}));

const stableT = (key: string, values?: Record<string, string | number>): string =>
  values?.count !== undefined ? `${key}:${String(values.count)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return {
    ...actual,
    rewindToMessage: (...args: unknown[]) => rewindToMessageMock(...args),
  };
});

const makeMessage = (id: string, role: Message['role']): Message => ({
  messageId: id,
  chatId: 'c1',
  createdAt: new Date(),
  content: '',
  role,
});

const renderDialog = (messageIndex = 2) => {
  const onOpenChange = vi.fn();
  render(
    <RewindDialog
      open
      onOpenChange={onOpenChange}
      chatId="c1"
      messageId="u2"
      messageIndex={messageIndex}
    />,
  );
  return { onOpenChange };
};

describe('RewindDialog', () => {
  beforeEach(() => {
    rewindToMessageMock.mockReset();
    toastMock.mockReset();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows both scope options and defaults to conversation+files', () => {
    useChatStore.setState({ messages: [], loading: false });
    renderDialog();
    expect(screen.getByText('scopeTitle')).toBeInTheDocument();
    expect(screen.getByText('scopeConversation')).toBeInTheDocument();
    expect(screen.getByText('scopeBoth')).toBeInTheDocument();
    expect(screen.getByText('scopeBothDesc')).toBeInTheDocument();
  });

  it('previews revertible file changes for assistant messages', async () => {
    useChatStore.setState({
      messages: [makeMessage('u1', 'user'), makeMessage('a1', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          path: '/work/a.txt',
          operation: 'write',
          has_original: true,
          timestamp: 1,
          revertible: true,
        },
      ],
    });
    vi.stubGlobal('fetch', fetchMock);
    renderDialog(1);
    await waitFor(() => {
      expect(screen.getByText('fileRevertSummary:1')).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/files/revert/changes/c1/a1',
      expect.objectContaining({ headers: expect.anything() }),
    );
  });

  it('shows empty hint when no snapshots exist', async () => {
    useChatStore.setState({
      messages: [makeMessage('u1', 'user'), makeMessage('a1', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    renderDialog(1);
    await waitFor(() => {
      expect(screen.getByText('noFileSnapshots')).toBeInTheDocument();
    });
  });

  it('rewinds conversation-only scope and truncates messages', async () => {
    useChatStore.setState({
      messages: [
        makeMessage('u0', 'user'),
        makeMessage('a0', 'assistant'),
        makeMessage('u2', 'user'),
      ],
      loading: false,
    });
    rewindToMessageMock.mockResolvedValue({
      data: {
        success: true,
        deleted_count: 2,
        composer_text: 'hello world',
        message_index: 1,
        goal_paused: false,
        reverted_files: [],
      },
    });
    renderDialog();
    fireEvent.click(screen.getByText('scopeConversation'));
    fireEvent.click(screen.getByText('confirm'));
    await waitFor(() => {
      expect(rewindToMessageMock).toHaveBeenCalledWith('c1', 'u2', 'conversation');
    });
    expect(useChatStore.getState().messages).toHaveLength(2);
    expect(useChatStore.getState().inputMessage).toBe('hello world');
  });

  it('shows files-reverted toast when both scope reverts files', async () => {
    useChatStore.setState({
      messages: [
        makeMessage('u0', 'user'),
        makeMessage('a0', 'assistant'),
        makeMessage('u2', 'user'),
      ],
      loading: false,
    });
    rewindToMessageMock.mockResolvedValue({
      data: {
        success: true,
        deleted_count: 2,
        composer_text: 'hello',
        message_index: 1,
        goal_paused: false,
        reverted_files: ['/work/a.txt'],
      },
    });
    renderDialog();
    fireEvent.click(screen.getByText('confirm'));
    await waitFor(() => {
      expect(rewindToMessageMock).toHaveBeenCalledWith('c1', 'u2', 'both');
    });
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ description: 'filesRevertedToast:1' }),
    );
  });

  it('blocks rewind while the agent is streaming', () => {
    useChatStore.setState({ messages: [], loading: true });
    renderDialog();
    fireEvent.click(screen.getByText('confirm'));
    expect(rewindToMessageMock).not.toHaveBeenCalled();
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ description: 'streamingBlocked' }),
    );
  });
});
