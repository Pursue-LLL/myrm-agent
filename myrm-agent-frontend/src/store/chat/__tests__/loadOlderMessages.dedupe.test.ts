import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import { loadOlderMessages } from '@/store/chat/messageManagement';

const getMessagesMock = vi.hoisted(() => vi.fn());
const mockGetState = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(),
  getMessages: (...args: unknown[]) => getMessagesMock(...args),
  generateChatTitle: vi.fn(),
  updateChatTitle: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn().mockResolvedValue({ active: false }),
  ApiError: class ApiError extends Error {
    code: number;
    constructor(code: number) {
      super('api error');
      this.code = code;
    }
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => mockGetState(),
  },
}));

describe('loadOlderMessages deduplication', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('filters out older messages that already exist in state to prevent duplicate keys', async () => {
    const existingMessages: Message[] = [
      {
        id: 'msg-2',
        role: 'user',
        content: 'Existing message 2',
        chat_id: 'chat-1',
        created_at: '2026-08-22T00:01:00Z',
      },
      {
        id: 'msg-3',
        role: 'assistant',
        content: 'Existing message 3',
        chat_id: 'chat-1',
        created_at: '2026-08-22T00:02:00Z',
      },
    ];

    const state: ChatState = {
      chatId: 'chat-1',
      messages: [...existingMessages],
      hasMoreMessages: true,
      nextCursor: 'cursor-123',
      loadingOlder: false,
    } as unknown as ChatState;

    mockGetState.mockReturnValue(state);

    const setMessages = (updater: (s: ChatState) => void) => {
      updater(state);
    };

    getMessagesMock.mockResolvedValueOnce({
      messages: [
        {
          id: 'msg-1',
          role: 'user',
          content: 'Older message 1',
          chat_id: 'chat-1',
          created_at: '2026-08-22T00:00:00Z',
        },
        {
          id: 'msg-2', // Duplicate with existing message
          role: 'user',
          content: 'Existing message 2 duplicate from server',
          chat_id: 'chat-1',
          created_at: '2026-08-22T00:01:00Z',
        },
      ],
      has_more: false,
      next_cursor: null,
    });

    await loadOlderMessages({ setMessages } as any);

    expect(state.loadingOlder).toBe(false);
    expect(state.hasMoreMessages).toBe(false);
    expect(state.messages).toHaveLength(3);
    expect(state.messages.map((m) => m.id)).toEqual(['msg-1', 'msg-2', 'msg-3']);
  });
});
