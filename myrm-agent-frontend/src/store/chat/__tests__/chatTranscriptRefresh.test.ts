import { beforeEach, describe, expect, it, vi } from 'vitest';

import { refreshOpenChatTranscript } from '@/store/chat/chatTranscriptRefresh';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

const getMessagesMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getMessages: (...args: unknown[]) => getMessagesMock(...args),
}));

const CHAT_ID = 'chat-a';

function message(messageId: string, role: Message['role'], content: string, minute: number): Message {
  return {
    messageId,
    chatId: CHAT_ID,
    role,
    content,
    createdAt: new Date(Date.UTC(2026, 9, 15, 0, minute)),
  };
}

function page(messages: Message[], hasMore = false, nextCursor: string | null = null) {
  return { messages, has_more: hasMore, next_cursor: nextCursor };
}

function seedStore(messages: Message[], extra: Partial<ReturnType<typeof useChatStore.getState>> = {}) {
  useChatStore.setState({
    chatId: CHAT_ID,
    loading: false,
    abortController: null,
    messages,
    hasMoreMessages: true,
    nextCursor: 'older-cursor',
    files: [],
    activeKnowledgeBaseIds: [],
    ...extra,
  });
}

function contents(): string[] {
  return useChatStore.getState().messages.map((m) => `${m.messageId}:${m.content}`);
}

describe('refreshOpenChatTranscript', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('replaces overlapping rows with the persisted version and appends rows only the DB holds', async () => {
    seedStore([message('u1', 'user', 'go', 1), message('a1', 'assistant', 'paused', 2)]);
    getMessagesMock.mockResolvedValue(
      page([
        message('u1', 'user', 'go', 1),
        message('a1', 'assistant', 'continued after timeout', 2),
        message('a2', 'assistant', 'done', 3),
      ]),
    );

    await refreshOpenChatTranscript(CHAT_ID);

    expect(contents()).toEqual(['u1:go', 'a1:continued after timeout', 'a2:done']);
  });

  it('keeps older pages the user already loaded and their cursor', async () => {
    seedStore([message('u0', 'user', 'old', 0), message('u1', 'user', 'go', 1)]);
    getMessagesMock.mockResolvedValue(page([message('u1', 'user', 'go', 1), message('a1', 'assistant', 'answer', 2)]));

    await refreshOpenChatTranscript(CHAT_ID);

    expect(contents()).toEqual(['u0:old', 'u1:go', 'a1:answer']);
    expect(useChatStore.getState().nextCursor).toBe('older-cursor');
    expect(useChatStore.getState().hasMoreMessages).toBe(true);
  });

  it('restarts from the fresh tail when the chat moved past everything held locally', async () => {
    seedStore([message('u1', 'user', 'go', 1)]);
    getMessagesMock.mockResolvedValue(
      page([message('x1', 'user', 'new', 30), message('x2', 'assistant', 'new answer', 31)], true, 'tail-cursor'),
    );

    await refreshOpenChatTranscript(CHAT_ID);

    expect(contents()).toEqual(['x1:new', 'x2:new answer']);
    expect(useChatStore.getState().nextCursor).toBe('tail-cursor');
    expect(useChatStore.getState().hasMoreMessages).toBe(true);
  });

  it('keeps composer state, loading flags and the transcript identity of untouched rows', async () => {
    seedStore([message('u1', 'user', 'go', 1)], {
      files: [{ name: 'report.pdf' } as never],
      mentionReferences: [{ id: 'm1' } as never],
      activeKnowledgeBaseIds: ['kb-1'],
    });
    const loadingTransitions: boolean[] = [];
    const unsubscribe = useChatStore.subscribe((state, prev) => {
      if (state.loading !== prev.loading) {
        loadingTransitions.push(state.loading);
      }
    });
    getMessagesMock.mockResolvedValue(page([message('u1', 'user', 'go', 1), message('a1', 'assistant', 'answer', 2)]));

    await refreshOpenChatTranscript(CHAT_ID);
    unsubscribe();

    const state = useChatStore.getState();
    expect(state.files).toHaveLength(1);
    expect(state.mentionReferences).toHaveLength(1);
    expect(state.activeKnowledgeBaseIds).toEqual(['kb-1']);
    expect(loadingTransitions).toEqual([]);
    expect(contents()).toEqual(['u1:go', 'a1:answer']);
  });

  it.each([
    ['another chat is open', { chatId: 'chat-b' }],
    ['a turn is streaming', { loading: true }],
    ['a stream controller is attached', { abortController: new AbortController() }],
  ])('does not fetch when %s', async (_label, override) => {
    seedStore([message('u1', 'user', 'go', 1)], override);

    await refreshOpenChatTranscript(CHAT_ID);

    expect(getMessagesMock).not.toHaveBeenCalled();
  });

  it('does nothing without a chat id', async () => {
    seedStore([message('u1', 'user', 'go', 1)]);

    await refreshOpenChatTranscript(undefined);

    expect(getMessagesMock).not.toHaveBeenCalled();
  });

  it('discards the fetched page when a turn started while the request was in flight', async () => {
    seedStore([message('u1', 'user', 'go', 1)]);
    getMessagesMock.mockImplementation(async () => {
      useChatStore.setState({ loading: true });
      return page([message('u1', 'user', 'go', 1), message('a1', 'assistant', 'stale', 2)]);
    });

    await refreshOpenChatTranscript(CHAT_ID);

    expect(contents()).toEqual(['u1:go']);
  });

  it('leaves the transcript and error flags untouched when the fetch fails', async () => {
    seedStore([message('u1', 'user', 'go', 1)], { loadError: false, isMessagesLoaded: true });
    getMessagesMock.mockRejectedValue(new Error('offline'));
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    await refreshOpenChatTranscript(CHAT_ID);

    expect(contents()).toEqual(['u1:go']);
    expect(useChatStore.getState().loadError).toBe(false);
    expect(useChatStore.getState().isMessagesLoaded).toBe(true);
    consoleError.mockRestore();
  });

  it('ignores an empty page instead of wiping the transcript', async () => {
    seedStore([message('u1', 'user', 'go', 1)]);
    getMessagesMock.mockResolvedValue(page([]));

    await refreshOpenChatTranscript(CHAT_ID);

    expect(contents()).toEqual(['u1:go']);
  });

  it('coalesces concurrent refreshes of the same chat into one request', async () => {
    seedStore([message('u1', 'user', 'go', 1)]);
    getMessagesMock.mockResolvedValue(page([message('u1', 'user', 'go', 1)]));

    await Promise.all([refreshOpenChatTranscript(CHAT_ID), refreshOpenChatTranscript(CHAT_ID)]);

    expect(getMessagesMock).toHaveBeenCalledTimes(1);
  });
});
