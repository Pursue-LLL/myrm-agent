import { beforeEach, describe, expect, it, vi } from 'vitest';

import { mergeStoredTail, refreshOpenChatTranscript } from '@/store/chat/chatTranscriptRefresh';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

const getMessagesMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getMessages: (...args: unknown[]) => getMessagesMock(...args),
}));

const CHAT_ID = 'chat-a';

function message(messageId: string, role: Message['role'], content: string, extra: Partial<Message> = {}): Message {
  return { messageId, chatId: CHAT_ID, role, content, createdAt: new Date(Date.UTC(2026, 9, 15)), ...extra };
}

/** A user row is stored under its request id; an assistant row is stored under a UUID and names that request. */
function storedAssistant(uuid: string, requestId: string, content: string): Message {
  return message(uuid, 'assistant', content, { requestMessageId: requestId });
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

function ids(messages: Message[] | null): string[] {
  return (messages ?? []).map((m) => m.messageId);
}

describe('mergeStoredTail', () => {
  it('does not show a streamed turn twice once its stored twin arrives under a UUID', () => {
    const local = [message('r-1', 'user', 'go'), message('r-1', 'assistant', 'answer', { routingTier: 'simple' })];
    const tail = [message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'answer')];

    expect(mergeStoredTail(local, tail)).toBe(local);
  });

  it('adds the continuation of a paused turn right behind it', () => {
    const local = [
      message('r-1', 'user', 'go'),
      message('r-1', 'assistant', 'paused'),
      message('r-2', 'user', 'next question'),
    ];
    const tail = [
      message('r-1', 'user', 'go'),
      storedAssistant('uuid-1', 'r-1', 'paused'),
      storedAssistant('uuid-2', 'r-1', 'continued after timeout'),
      message('r-2', 'user', 'next question'),
    ];

    expect(ids(mergeStoredTail(local, tail))).toEqual(['r-1', 'r-1', 'uuid-2', 'r-2']);
  });

  it('recognises rows hydrated from the DB by id and by their request id alike', () => {
    const local = [message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'answer')];
    const tail = [message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'answer')];

    expect(mergeStoredTail(local, tail)).toBe(local);
  });

  it('keeps a user row and an assistant row with the same raw id apart', () => {
    const local = [message('r-1', 'user', 'go')];
    const tail = [message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'answer')];

    expect(ids(mergeStoredTail(local, tail))).toEqual(['r-1', 'uuid-1']);
  });

  it('appends rows of turns the screen has never seen', () => {
    const local = [message('r-1', 'user', 'go'), message('r-1', 'assistant', 'answer')];
    const notice = message('uuid-9', 'assistant', 'background job finished');
    const tail = [message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'answer'), notice];

    expect(mergeStoredTail(local, tail)).toEqual([...local, notice]);
  });

  it('leaves rows on screen untouched, including local-only rows and injected fields', () => {
    const streamed = message('r-1', 'assistant', 'answer', { routingTier: 'simple' });
    const localOnly = message('local-only', 'assistant', 'never stored');
    const local = [message('r-1', 'user', 'go'), streamed, localOnly];
    const tail = [
      message('r-1', 'user', 'go'),
      storedAssistant('uuid-1', 'r-1', 'answer'),
      message('uuid-9', 'user', 'x'),
    ];

    const merged = mergeStoredTail(local, tail);

    expect(merged?.slice(0, 3)).toEqual(local);
    expect(merged?.[1]).toBe(streamed);
  });

  it('reports no overlap when the tail shares nothing with the screen', () => {
    expect(mergeStoredTail([message('r-1', 'user', 'go')], [message('r-9', 'user', 'new')])).toBeNull();
  });
});

describe('refreshOpenChatTranscript', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('adds the rows only the DB holds and keeps older pages with their cursor', async () => {
    seedStore([message('u0', 'user', 'old'), message('r-1', 'user', 'go'), message('r-1', 'assistant', 'paused')]);
    getMessagesMock.mockResolvedValue(
      page([
        message('r-1', 'user', 'go'),
        storedAssistant('uuid-1', 'r-1', 'paused'),
        storedAssistant('uuid-2', 'r-1', 'continued'),
      ]),
    );

    await refreshOpenChatTranscript(CHAT_ID);

    const state = useChatStore.getState();
    expect(ids(state.messages)).toEqual(['u0', 'r-1', 'r-1', 'uuid-2']);
    expect(state.nextCursor).toBe('older-cursor');
    expect(state.hasMoreMessages).toBe(true);
  });

  it('does not touch the store when every stored row is already on screen', async () => {
    seedStore([message('r-1', 'user', 'go'), message('r-1', 'assistant', 'answer')]);
    const before = useChatStore.getState().messages;
    getMessagesMock.mockResolvedValue(page([message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'answer')]));

    await refreshOpenChatTranscript(CHAT_ID);

    expect(useChatStore.getState().messages).toBe(before);
  });

  it('restarts from the fresh tail when the chat moved past everything held locally', async () => {
    seedStore([message('r-1', 'user', 'go')]);
    getMessagesMock.mockResolvedValue(
      page([message('r-9', 'user', 'new'), storedAssistant('uuid-9', 'r-9', 'new answer')], true, 'tail-cursor'),
    );

    await refreshOpenChatTranscript(CHAT_ID);

    const state = useChatStore.getState();
    expect(ids(state.messages)).toEqual(['r-9', 'uuid-9']);
    expect(state.nextCursor).toBe('tail-cursor');
    expect(state.hasMoreMessages).toBe(true);
  });

  it('keeps composer state and never toggles loading', async () => {
    seedStore([message('r-1', 'user', 'go')], {
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
    getMessagesMock.mockResolvedValue(page([message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'answer')]));

    await refreshOpenChatTranscript(CHAT_ID);
    unsubscribe();

    const state = useChatStore.getState();
    expect(state.files).toHaveLength(1);
    expect(state.mentionReferences).toHaveLength(1);
    expect(state.activeKnowledgeBaseIds).toEqual(['kb-1']);
    expect(loadingTransitions).toEqual([]);
    expect(ids(state.messages)).toEqual(['r-1', 'uuid-1']);
  });

  it.each([
    ['another chat is open', { chatId: 'chat-b' }],
    ['a turn is streaming', { loading: true }],
    ['a stream controller is attached', { abortController: new AbortController() }],
  ])('does not fetch when %s', async (_label, override) => {
    seedStore([message('r-1', 'user', 'go')], override);

    await refreshOpenChatTranscript(CHAT_ID);

    expect(getMessagesMock).not.toHaveBeenCalled();
  });

  it('does nothing without a chat id', async () => {
    seedStore([message('r-1', 'user', 'go')]);

    await refreshOpenChatTranscript(undefined);

    expect(getMessagesMock).not.toHaveBeenCalled();
  });

  it('discards the fetched page when a turn started while the request was in flight', async () => {
    seedStore([message('r-1', 'user', 'go')]);
    getMessagesMock.mockImplementation(async () => {
      useChatStore.setState({ loading: true });
      return page([message('r-1', 'user', 'go'), storedAssistant('uuid-1', 'r-1', 'stale')]);
    });

    await refreshOpenChatTranscript(CHAT_ID);

    expect(ids(useChatStore.getState().messages)).toEqual(['r-1']);
  });

  it('leaves the transcript and error flags untouched when the fetch fails', async () => {
    seedStore([message('r-1', 'user', 'go')], { loadError: false, isMessagesLoaded: true });
    getMessagesMock.mockRejectedValue(new Error('offline'));
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    await refreshOpenChatTranscript(CHAT_ID);

    expect(ids(useChatStore.getState().messages)).toEqual(['r-1']);
    expect(useChatStore.getState().loadError).toBe(false);
    expect(useChatStore.getState().isMessagesLoaded).toBe(true);
    consoleError.mockRestore();
  });

  it('ignores an empty page instead of wiping the transcript', async () => {
    seedStore([message('r-1', 'user', 'go')]);
    getMessagesMock.mockResolvedValue(page([]));

    await refreshOpenChatTranscript(CHAT_ID);

    expect(ids(useChatStore.getState().messages)).toEqual(['r-1']);
  });

  it('coalesces concurrent refreshes of the same chat into one request', async () => {
    seedStore([message('r-1', 'user', 'go')]);
    getMessagesMock.mockResolvedValue(page([message('r-1', 'user', 'go')]));

    await Promise.all([refreshOpenChatTranscript(CHAT_ID), refreshOpenChatTranscript(CHAT_ID)]);

    expect(getMessagesMock).toHaveBeenCalledTimes(1);
  });
});
