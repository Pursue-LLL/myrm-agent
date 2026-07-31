/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockSendMessage = vi.fn();
const mockInitializeChat = vi.fn();
const mockAddPane = vi.fn();

const chatState = vi.hoisted(() => ({
  chatId: null as string | null,
  loading: false,
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      chatId: chatState.chatId,
      loading: chatState.loading,
      sendMessage: mockSendMessage,
      initializeChat: mockInitializeChat,
    }),
  },
}));

vi.mock('@/store/useWorkspaceStore', () => ({
  default: {
    getState: () => ({
      panes: [],
      addPane: mockAddPane,
    }),
  },
}));

import { submitLearnMessage } from '../submitLearnMessage';

describe('submitLearnMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatState.chatId = null;
    chatState.loading = false;
    mockSendMessage.mockResolvedValue(undefined);
    mockInitializeChat.mockImplementation(() => {
      chatState.chatId = 'new-chat-abc';
    });
  });

  it('bootstraps chat via initializeChat when chatId is missing', async () => {
    const result = await submitLearnMessage({ input: '/learn URL: https://example.com' });

    expect(mockInitializeChat).toHaveBeenCalledWith(undefined);
    expect(mockAddPane).toHaveBeenCalledWith('new-chat-abc');
    expect(mockSendMessage).toHaveBeenCalledWith('/learn URL: https://example.com');
    expect(result).toEqual({
      ok: true,
      message: '/learn URL: https://example.com',
      chatId: 'new-chat-abc',
    });
  });
});
