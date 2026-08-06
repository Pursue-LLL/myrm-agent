import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const searchChatHistoryMock = vi.hoisted(() => vi.fn());
const suggestReferencesMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', () => ({
  searchChatHistory: (...args: unknown[]) => searchChatHistoryMock(...args),
  suggestReferences: (...args: unknown[]) => suggestReferencesMock(...args),
}));

vi.mock('@/store/useAgentStore', () => ({
  default: {
    getState: () => ({ agents: [], fetchAgents: vi.fn(async () => undefined) }),
  },
}));

const chatStoreRef = vi.hoisted(() => ({
  state: {
    chatId: 'composer-chat',
    fetchAgents: vi.fn(),
    setInputMessage: vi.fn(),
    addMentionReference: vi.fn(),
  },
}));

vi.mock('@/store/useChatStore', () => {
  const useChatStore = ((selector: (state: typeof chatStoreRef.state) => unknown) =>
    selector(chatStoreRef.state)) as unknown as {
    (selector: (state: typeof chatStoreRef.state) => unknown): unknown;
    getState: () => typeof chatStoreRef.state;
  };
  useChatStore.getState = () => chatStoreRef.state;
  return { default: useChatStore };
});

import { useReferenceMention } from '@/hooks/message-input/useReferenceMention';

describe('useReferenceMention chat mode', () => {
  beforeEach(() => {
    searchChatHistoryMock.mockReset();
    suggestReferencesMock.mockReset();
    chatStoreRef.state.chatId = 'composer-chat';
    chatStoreRef.state.addMentionReference = vi.fn();
  });

  it('loads prior chat suggestions for @chat: queries', async () => {
    searchChatHistoryMock.mockResolvedValue({
      items: [
        {
          chat_id: 'prior-chat-1',
          chat_title: 'Alpha planning',
          snippet: 'Redis caching decision',
        },
      ],
    });

    const { result, rerender } = renderHook(
      ({ message, cursor }: { message: string; cursor: number }) =>
        useReferenceMention(message, cursor),
      { initialProps: { message: '@chat:Alpha', cursor: '@chat:Alpha'.length } },
    );

    await waitFor(() => {
      expect(result.current.results.some((item) => item.reference_type === 'prior_chat')).toBe(true);
    });

    expect(searchChatHistoryMock).toHaveBeenCalledWith('Alpha', 20, 0);
    expect(suggestReferencesMock).not.toHaveBeenCalled();

    rerender({ message: '@chat:Alpha', cursor: '@chat:Alpha'.length });
  });

  it('adds prior_chat mention reference on select', async () => {
    searchChatHistoryMock.mockResolvedValue({
      items: [
        {
          chat_id: 'prior-chat-1',
          chat_title: 'Alpha planning',
          snippet: 'Redis caching decision',
        },
      ],
    });

    const { result } = renderHook(() => useReferenceMention('@chat:Alpha', '@chat:Alpha'.length));

    await waitFor(() => {
      expect(result.current.results.length).toBeGreaterThan(0);
    });

    act(() => {
      result.current.selectReference(result.current.results[0], chatStoreRef.state.setInputMessage);
    });

    expect(chatStoreRef.state.addMentionReference).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'prior_chat',
        path: 'prior-chat-1',
        fileId: 'prior-chat-1',
      }),
    );
  });
});
