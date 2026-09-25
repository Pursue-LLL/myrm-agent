import { describe, it, expect, vi, beforeEach } from 'vitest';
import { autoSaveChat } from '../messageManagement';
import type { Message } from '../types';

vi.mock('@/services/chat', () => ({
  updateChatTitle: vi.fn().mockResolvedValue({}),
  generateChatTitle: vi.fn().mockResolvedValue('Generated Title'),
  getChatDetail: vi.fn(),
  getMessages: vi.fn(),
  getContextPins: vi.fn(),
  listContextBranches: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: vi.fn().mockReturnValue({
      chatHistoryItems: [],
      setChatHistoryItems: vi.fn(),
    }),
  },
}));

vi.mock('@/store/useConfigStore', () => ({
  default: {
    getState: vi.fn().mockReturnValue({
      enableAutoTitleGeneration: true,
    }),
  },
}));

vi.mock('@/store/useWorkspaceStore', () => ({
  default: {
    getState: vi.fn().mockReturnValue({
      panes: [],
    }),
  },
}));

vi.mock('@/store/useProjectStore', () => ({
  useProjectStore: {
    getState: vi.fn().mockReturnValue({
      activeFilter: null,
    }),
  },
}));

describe('autoSaveChat lazy session persistence gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('skips title generation and sidebar update when no assistant message exists', async () => {
    const { updateChatTitle } = await import('@/services/chat');

    const userOnlyMessages: Message[] = [
      {
        messageId: 'u1',
        chatId: 'chat-blank-1',
        role: 'user',
        content: 'Hello, world!',
        createdAt: new Date(),
      },
    ];

    await autoSaveChat('chat-blank-1', userOnlyMessages, 'agent', false);

    expect(updateChatTitle).not.toHaveBeenCalled();
  });

  it('proceeds with title generation and sidebar update when assistant message exists', async () => {
    const { updateChatTitle } = await import('@/services/chat');

    const fullMessages: Message[] = [
      {
        messageId: 'u1',
        chatId: 'chat-valid-1',
        role: 'user',
        content: 'Hello, world!',
        createdAt: new Date(),
      },
      {
        messageId: 'a1',
        chatId: 'chat-valid-1',
        role: 'assistant',
        content: 'Hi there! How can I help you?',
        createdAt: new Date(),
      },
    ];

    await autoSaveChat('chat-valid-1', fullMessages, 'agent', false);

    expect(updateChatTitle).toHaveBeenCalledWith('chat-valid-1', 'Generated Title');
  });
});
