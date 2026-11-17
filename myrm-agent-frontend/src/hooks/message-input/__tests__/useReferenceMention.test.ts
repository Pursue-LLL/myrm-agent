import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const searchCitableChatsMock = vi.hoisted(() => vi.fn());
const suggestReferencesMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', () => ({
  searchCitableChats: (...args: unknown[]) => searchCitableChatsMock(...args),
  suggestReferences: (...args: unknown[]) => suggestReferencesMock(...args),
}));

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
}));

const mockAgents = [
  {
    id: 'strategic-advisor',
    name: 'Strategic Advisor',
    description: 'Readonly strategy and risk advisor',
    avatar_url: null,
  },
  { id: 'code-reviewer', name: 'Code Reviewer', description: 'Code quality and review specialist', avatar_url: null },
];

vi.mock('@/store/useAgentStore', () => ({
  default: {
    getState: () => ({ agents: mockAgents, fetchAgents: vi.fn(async () => undefined) }),
  },
}));

const chatStoreRef = vi.hoisted(() => ({
  state: {
    chatId: 'composer-chat' as string | undefined,
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
import { DEBOUNCE_MS } from '@/hooks/message-input/useReferenceMentionUtils';
import { HISTORY_SEARCH_MAX_LENGTH } from '@/lib/constants/chat-history-search';

describe('useReferenceMention chat mode', () => {
  beforeEach(() => {
    searchCitableChatsMock.mockReset();
    suggestReferencesMock.mockReset();
    chatStoreRef.state.chatId = 'composer-chat';
    chatStoreRef.state.addMentionReference = vi.fn();
  });

  it('loads prior chat suggestions for @chat: queries', async () => {
    searchCitableChatsMock.mockResolvedValue({
      items: [
        {
          chat_id: 'prior-chat-1',
          chat_title: 'Alpha planning',
          snippet: 'Redis caching decision',
        },
      ],
    });

    const { result, rerender } = renderHook(
      ({ message, cursor }: { message: string; cursor: number }) => useReferenceMention(message, cursor),
      { initialProps: { message: '@chat:Alpha', cursor: '@chat:Alpha'.length } },
    );

    await waitFor(() => {
      expect(result.current.results.some((item) => item.reference_type === 'prior_chat')).toBe(true);
    });

    expect(searchCitableChatsMock).toHaveBeenCalledWith('Alpha', 20, 0, 'composer-chat');
    expect(suggestReferencesMock).not.toHaveBeenCalled();

    rerender({ message: '@chat:Alpha', cursor: '@chat:Alpha'.length });
  });

  it('adds prior_chat mention reference on select', async () => {
    searchCitableChatsMock.mockResolvedValue({
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
        viaText: true,
      }),
    );
  });

  it('loads prior chat suggestions on EmptyChat when chatId is undefined', async () => {
    chatStoreRef.state.chatId = undefined;
    searchCitableChatsMock.mockResolvedValue({
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
      expect(result.current.results.some((item) => item.reference_type === 'prior_chat')).toBe(true);
    });

    expect(searchCitableChatsMock).toHaveBeenCalledWith('Alpha', 20, 0, undefined);
    expect(suggestReferencesMock).not.toHaveBeenCalled();
  });

  it('does not search prior chats until something follows @chat:, because the server refuses an empty query', () => {
    vi.useFakeTimers();
    try {
      renderHook(() => useReferenceMention('@chat:', '@chat:'.length));

      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS * 2);
      });

      expect(searchCitableChatsMock).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('sends at most the characters the server accepts of a long paste that has no space to end the mention', async () => {
    searchCitableChatsMock.mockResolvedValue({ items: [] });
    const message = `@chat:${'长'.repeat(HISTORY_SEARCH_MAX_LENGTH + 100)}`;

    renderHook(() => useReferenceMention(message, message.length));

    await waitFor(() => {
      expect(searchCitableChatsMock).toHaveBeenCalledWith(
        '长'.repeat(HISTORY_SEARCH_MAX_LENGTH),
        20,
        0,
        'composer-chat',
      );
    });
  });

  it('cuts that query by character, so a character outside the basic plane is never split in half', async () => {
    searchCitableChatsMock.mockResolvedValue({ items: [] });
    const message = `@chat:a${'𠮷'.repeat(HISTORY_SEARCH_MAX_LENGTH + 100)}`;

    renderHook(() => useReferenceMention(message, message.length));

    await waitFor(() => {
      expect(searchCitableChatsMock).toHaveBeenCalledWith(
        `a${'𠮷'.repeat(HISTORY_SEARCH_MAX_LENGTH - 1)}`,
        20,
        0,
        'composer-chat',
      );
    });
  });
});

describe('useReferenceMention EmptyChat @Agent bug recovery', () => {
  beforeEach(() => {
    searchCitableChatsMock.mockReset();
    suggestReferencesMock.mockReset();
    chatStoreRef.state.chatId = undefined; // EmptyChat
    chatStoreRef.state.addMentionReference = vi.fn();
    chatStoreRef.state.setInputMessage = vi.fn();
  });

  it('synchronously surfaces available digital employees on EmptyChat when @ is typed', () => {
    const { result } = renderHook(() => useReferenceMention('@', 1));

    expect(result.current.isOpen).toBe(true);
    const agentSuggestions = result.current.results.filter((item) => item.reference_type === 'agent');
    expect(agentSuggestions.length).toBe(2);
    expect(agentSuggestions[0].file_id).toBe('strategic-advisor');
    expect(agentSuggestions[1].file_id).toBe('code-reviewer');
  });

  it('filters digital employees by name on EmptyChat when @code is typed', async () => {
    const { result } = renderHook(() => useReferenceMention('@code', 5));

    await waitFor(() => {
      const agentSuggestions = result.current.results.filter((item) => item.reference_type === 'agent');
      expect(agentSuggestions.length).toBe(1);
      expect(agentSuggestions[0].file_id).toBe('code-reviewer');
    });
  });

  it('successfully selects and registers agent MentionReference on EmptyChat', async () => {
    const { result } = renderHook(() => useReferenceMention('@code', 5));

    await waitFor(() => {
      expect(result.current.results.length).toBeGreaterThan(0);
    });

    const targetAgent = result.current.results.find((item) => item.file_id === 'code-reviewer');
    expect(targetAgent).toBeDefined();

    act(() => {
      if (targetAgent) {
        result.current.selectReference(targetAgent, chatStoreRef.state.setInputMessage);
      }
    });

    expect(chatStoreRef.state.setInputMessage).toHaveBeenCalledWith('@Code Reviewer ');
    expect(chatStoreRef.state.addMentionReference).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'agent',
        fileId: 'code-reviewer',
        label: '@Code Reviewer',
        source: 'agent',
        viaText: true,
      }),
    );
  });
});

describe('useReferenceMention while it is still searching', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    searchCitableChatsMock.mockReset();
    suggestReferencesMock.mockReset();
    chatStoreRef.state.chatId = 'composer-chat';
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** A request that stays open until the test settles it. */
  function pending<T>() {
    let resolve!: (value: T) => void;
    let reject!: (reason: Error) => void;
    const promise = new Promise<T>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  const elapse = (ms: number) =>
    act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });

  const settle = (action: () => void) =>
    act(async () => {
      action();
    });

  it('searches from the keystroke until the prior conversations arrive, so no match is claimed in between', async () => {
    const request = pending<{ items: never[] }>();
    searchCitableChatsMock.mockReturnValue(request.promise);
    const { result } = renderHook(() => useReferenceMention('@chat:Alpha', '@chat:Alpha'.length));

    expect(result.current.isSearching).toBe(true);
    await elapse(DEBOUNCE_MS);
    expect(searchCitableChatsMock).toHaveBeenCalledTimes(1);
    expect(result.current.isSearching).toBe(true);

    await settle(() => request.resolve({ items: [] }));
    expect(result.current.isSearching).toBe(false);
  });

  it('does not search after a bare @chat:, which never reaches the server', async () => {
    const { result } = renderHook(() => useReferenceMention('@chat:', '@chat:'.length));

    expect(result.current.isOpen).toBe(true);
    expect(result.current.isSearching).toBe(false);
    await elapse(DEBOUNCE_MS * 2);
    expect(searchCitableChatsMock).not.toHaveBeenCalled();
    expect(result.current.isSearching).toBe(false);
  });

  it('stops searching when the prior conversation search fails', async () => {
    const request = pending<{ items: never[] }>();
    searchCitableChatsMock.mockReturnValue(request.promise);
    const { result } = renderHook(() => useReferenceMention('@chat:Alpha', '@chat:Alpha'.length));
    await elapse(DEBOUNCE_MS);

    await settle(() => request.reject(new Error('offline')));

    expect(result.current.isSearching).toBe(false);
    expect(result.current.results).toEqual([]);
  });

  it.each(['@src', '@folder:docs', '@wiki:notes'])(
    'searches the workspace from the keystroke on %s until the answer arrives',
    async (message) => {
      const request = pending<{ results: never[] }>();
      suggestReferencesMock.mockReturnValue(request.promise);
      const { result } = renderHook(() => useReferenceMention(message, message.length));

      expect(result.current.isSearching).toBe(true);
      await elapse(DEBOUNCE_MS);
      expect(suggestReferencesMock).toHaveBeenCalledTimes(1);
      expect(result.current.isSearching).toBe(true);

      await settle(() => request.resolve({ results: [] }));
      expect(result.current.isSearching).toBe(false);
    },
  );

  it('does not search on EmptyChat, where there is no workspace to ask', async () => {
    chatStoreRef.state.chatId = undefined;
    const { result } = renderHook(() => useReferenceMention('@folder:docs', '@folder:docs'.length));

    expect(result.current.isSearching).toBe(false);
    await elapse(DEBOUNCE_MS * 2);
    expect(suggestReferencesMock).not.toHaveBeenCalled();
    expect(result.current.isSearching).toBe(false);
  });

  it('stops searching when the workspace search fails', async () => {
    const request = pending<{ results: never[] }>();
    suggestReferencesMock.mockReturnValue(request.promise);
    const { result } = renderHook(() => useReferenceMention('@src', '@src'.length));
    await elapse(DEBOUNCE_MS);

    await settle(() => request.reject(new Error('offline')));

    expect(result.current.isSearching).toBe(false);
  });

  it('stops searching when the mention is gone or dismissed', () => {
    suggestReferencesMock.mockReturnValue(pending<{ results: never[] }>().promise);
    const { result, rerender } = renderHook(
      ({ message }: { message: string }) => useReferenceMention(message, message.length),
      { initialProps: { message: '@src' } },
    );
    expect(result.current.isSearching).toBe(true);

    rerender({ message: 'plain text' });
    expect(result.current.isOpen).toBe(false);
    expect(result.current.isSearching).toBe(false);

    rerender({ message: '@src' });
    expect(result.current.isSearching).toBe(true);
    act(() => result.current.dismiss());
    expect(result.current.isSearching).toBe(false);
  });

  it('ignores the answer to an earlier keystroke and keeps searching until the latest one arrives', async () => {
    const first = pending<{ items: never[] }>();
    const second = pending<{ items: never[] }>();
    searchCitableChatsMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(
      ({ message }: { message: string }) => useReferenceMention(message, message.length),
      { initialProps: { message: '@chat:Al' } },
    );
    await elapse(DEBOUNCE_MS);
    rerender({ message: '@chat:Alp' });
    await elapse(DEBOUNCE_MS);
    expect(searchCitableChatsMock).toHaveBeenCalledTimes(2);

    await settle(() => first.resolve({ items: [] }));
    expect(result.current.isSearching).toBe(true);

    await settle(() => second.resolve({ items: [] }));
    expect(result.current.isSearching).toBe(false);
  });
});
