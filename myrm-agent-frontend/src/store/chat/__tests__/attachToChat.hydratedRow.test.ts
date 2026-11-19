/**
 * Reply of a turn that is still running when the page is reloaded.
 *
 * Real scenario: the page is reloaded after the user approved a tool card while the resumed run keeps writing, or right
 * after a message was sent. The transcript comes back from the DB (assistant rows carry UUID ids and name the streamed
 * request in `requestMessageId`), the page attaches to the running turn, and the stream it gets names the turn by its
 * request id.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchWithTimeout } from '@/lib/api';
import { parseMessages } from '@/store/chat/messageHydration';
import { attachToChat, type ChatActionsMethods } from '@/store/chat/messageRequest';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, fetchWithTimeout: vi.fn() };
});

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return { ...actual, getChatDetail: vi.fn(async () => ({ chat: {} })) };
});

const CHAT_ID = 'chat-1';
const REQUEST_ID = 'r-1';
const STORED_ID = '3f125655-a510-4c11-9a52-8a8f5d0c7e10';

const actions = {
  setMessages: (updater: Parameters<ChatActionsMethods['setMessages']>[0]) => useChatStore.setState(updater),
  setMessageAppeared: vi.fn(),
  setLoading: vi.fn(),
  setInputMessage: vi.fn(),
  clearActiveStream: vi.fn(),
  _processSuggestions: vi.fn(),
  scheduleAutoSave: vi.fn(),
} as unknown as ChatActionsMethods;

function sse(events: object[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
}

function hydratedRows(metadata: Record<string, unknown> = {}): Message[] {
  return parseMessages([
    { messageId: 'u-1', chatId: CHAT_ID, role: 'user', content: 'write the list', createdAt: new Date() },
    {
      messageId: STORED_ID,
      chatId: CHAT_ID,
      role: 'assistant',
      content: "I'll run that command now.",
      createdAt: new Date(),
      metadata: { request_message_id: REQUEST_ID, ...metadata },
    },
  ] as unknown as Message[]);
}

function finishedPreviousTurn(): Message[] {
  return parseMessages([
    { messageId: 'u-0', chatId: CHAT_ID, role: 'user', content: 'say hi', createdAt: new Date() },
    {
      messageId: '9d0c4f50-0000-4000-8000-000000000001',
      chatId: CHAT_ID,
      role: 'assistant',
      content: 'hi',
      createdAt: new Date(),
      metadata: { request_message_id: 'r-0' },
    },
  ] as unknown as Message[]);
}

function assistantRows(): Message[] {
  return useChatStore.getState().messages.filter((message) => message.role === 'assistant');
}

describe('attachToChat after a reload that hydrated the transcript from the DB', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      chatId: CHAT_ID,
      loading: false,
      abortController: null,
      actionMode: 'agent',
      messages: hydratedRows(),
    });
  });

  it('shows the whole reply of the running turn: the snapshot and every chunk that follows it', async () => {
    vi.mocked(fetchWithTimeout).mockResolvedValue(
      sse([
        {
          type: 'catchup_snapshot',
          messageId: REQUEST_ID,
          data: { content: 'one\ntwo\n', reasoning: '', progress_steps: [], sources: [] },
        },
        { type: 'message', messageId: REQUEST_ID, data: 'three\n' },
        { type: 'message', messageId: REQUEST_ID, data: 'four\n\nDONE' },
        { type: 'message_end', messageId: REQUEST_ID, completion_status: 'completed' },
      ]),
    );

    await attachToChat(CHAT_ID, actions, useChatStore.getState);
    await vi.waitFor(() => expect(useChatStore.getState().loading).toBe(false));
    // The message_end handler settles the row after a short delay.
    await new Promise((resolve) => setTimeout(resolve, 600));

    const rows = assistantRows();
    expect(rows.map((row) => row.content)).toEqual(['one\ntwo\nthree\nfour\n\nDONE']);
  });
  it('streams into the hydrated row of the turn and keeps its stored identity', async () => {
    vi.mocked(fetchWithTimeout).mockResolvedValue(
      sse([
        {
          type: 'catchup_snapshot',
          messageId: REQUEST_ID,
          data: { content: 'one\n', reasoning: '', progress_steps: [], sources: [] },
        },
        { type: 'message', messageId: REQUEST_ID, data: 'two' },
        { type: 'message_end', messageId: REQUEST_ID, completion_status: 'completed' },
      ]),
    );

    await attachToChat(CHAT_ID, actions, useChatStore.getState);
    await new Promise((resolve) => setTimeout(resolve, 600));

    const [row] = assistantRows();
    expect(row?.messageId).toBe(STORED_ID);
    expect(row?.requestMessageId).toBe(REQUEST_ID);
  });

  it('leaves the answer of the previous turn alone when the running turn has no row yet', async () => {
    useChatStore.setState({
      messages: [
        ...finishedPreviousTurn(),
        ...parseMessages([
          { messageId: 'u-1', chatId: CHAT_ID, role: 'user', content: 'write the list', createdAt: new Date() },
        ] as unknown as Message[]),
      ],
    });
    vi.mocked(fetchWithTimeout).mockResolvedValue(
      sse([
        {
          type: 'catchup_snapshot',
          messageId: REQUEST_ID,
          data: { content: 'one\n', reasoning: '', progress_steps: [], sources: [] },
        },
        { type: 'message', messageId: REQUEST_ID, data: 'two' },
        { type: 'message_end', messageId: REQUEST_ID, completion_status: 'completed' },
      ]),
    );

    await attachToChat(CHAT_ID, actions, useChatStore.getState);
    await new Promise((resolve) => setTimeout(resolve, 600));

    expect(assistantRows().map((row) => row.content)).toEqual(['hi', 'one\ntwo']);
  });

  describe('media generated before the page attached', () => {
    const image = { kind: 'image', task_id: 'img-1' };
    const speech = { kind: 'tts', media: 'media://media_a', model: 'voice-1' };

    async function attachWithSnapshot(data: Record<string, unknown>): Promise<Message | undefined> {
      vi.mocked(fetchWithTimeout).mockResolvedValue(
        sse([
          {
            type: 'catchup_snapshot',
            messageId: REQUEST_ID,
            data: { content: 'here it is\n', reasoning: '', progress_steps: [], sources: [], ...data },
          },
          { type: 'message_end', messageId: REQUEST_ID, completion_status: 'completed' },
        ]),
      );
      await attachToChat(CHAT_ID, actions, useChatStore.getState);
      await new Promise((resolve) => setTimeout(resolve, 600));
      return assistantRows()[0];
    }

    it('shows the cards the snapshot registers and drops entries that are not media', async () => {
      const row = await attachWithSnapshot({ media_generated: [image, speech, { kind: 'image' }] });

      expect(row?.metadata?.media_generated).toEqual([image, speech]);
    });

    it('lists a card once when the snapshot repeats media the page already showed', async () => {
      useChatStore.setState({ messages: hydratedRows({ media_generated: [image] }) });

      const row = await attachWithSnapshot({ media_generated: [image, speech] });

      expect(row?.metadata?.media_generated).toEqual([image, speech]);
    });

    it('keeps the cards already shown when the snapshot registers none', async () => {
      useChatStore.setState({ messages: hydratedRows({ media_generated: [image] }) });

      const row = await attachWithSnapshot({ media_generated: [] });

      expect(row?.metadata?.media_generated).toEqual([image]);
    });
  });
});
