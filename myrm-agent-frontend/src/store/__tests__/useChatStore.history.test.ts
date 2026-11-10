import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatHistoryResponse, ChatItem, PaginationInfo } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';
import { deferred } from '@/test-utils/deferred';

const getChatHistory = vi.hoisted(() =>
  vi.fn<
    (
      page: number,
      pageSize: number,
      source?: string,
      projectId?: string | null,
      keyword?: string,
    ) => Promise<ChatHistoryResponse>
  >(),
);

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  getChatHistory,
}));

const chat = (id: string, source = 'web'): ChatItem => ({
  id,
  title: `Title ${id}`,
  firstMessage: '',
  lastMessage: '',
  updatedAt: new Date(0),
  createdAt: new Date(0),
  actionMode: 'agent',
  source,
});

const pagination = (overrides: Partial<PaginationInfo> = {}): PaginationInfo => ({
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 1,
  has_next: false,
  has_prev: false,
  ...overrides,
});

const pageOf = (chats: ChatItem[], overrides: Partial<PaginationInfo> = {}): ChatHistoryResponse => ({
  items: chats,
  pagination: pagination({ total: chats.length, ...overrides }),
});

const state = () => useChatStore.getState();
const ids = () => state().chatHistoryItems.map((item) => item.id);
const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  getChatHistory.mockReset();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  useProjectStore.setState({ activeFilter: undefined });
  useChatStore.setState({
    chatHistoryItems: [],
    chatHistoryPagination: null,
    chatHistoryLoading: false,
    chatHistoryError: null,
    chatHistorySourceFilter: null,
    chatHistorySearchKeyword: '',
    chatHistoryAvailableSources: ['web'],
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('loadChatHistory', () => {
  it('lists the first page with its pagination and the sources found in it', async () => {
    getChatHistory.mockResolvedValue(
      pageOf([chat('a', 'web'), chat('b', 'cli'), chat('c', 'web')], { has_next: true }),
    );

    await state().loadChatHistory(1, 20);

    expect(getChatHistory).toHaveBeenCalledExactlyOnceWith(1, 20, undefined, undefined, undefined);
    expect(ids()).toEqual(['a', 'b', 'c']);
    expect(state().chatHistoryPagination?.has_next).toBe(true);
    expect(state().chatHistoryAvailableSources).toEqual(['cli', 'web']);
    expect(state().chatHistoryLoading).toBe(false);
    expect(state().chatHistoryError).toBeNull();
  });

  it('sends the source, project and trimmed keyword filters along', async () => {
    getChatHistory.mockResolvedValue(pageOf([]));
    useProjectStore.setState({ activeFilter: 'project-1' });
    useChatStore.setState({ chatHistorySourceFilter: 'cli', chatHistorySearchKeyword: '  plan  ' });

    await state().loadChatHistory(1, 20);

    expect(getChatHistory).toHaveBeenCalledExactlyOnceWith(1, 20, 'cli', 'project-1', 'plan');
  });

  it('keeps the source list it has while a source filter narrows the result', async () => {
    getChatHistory.mockResolvedValue(pageOf([chat('a', 'cli')]));
    useChatStore.setState({ chatHistorySourceFilter: 'cli', chatHistoryAvailableSources: ['cli', 'web'] });

    await state().loadChatHistory(1, 20);

    expect(state().chatHistoryAvailableSources).toEqual(['cli', 'web']);
  });

  it('keeps the source list it has when a page without chats arrives', async () => {
    getChatHistory.mockResolvedValue(pageOf([]));

    await state().loadChatHistory(1, 20);

    expect(state().chatHistoryAvailableSources).toEqual(['web']);
  });

  it('asks the server once while a load is in flight and not at all once the list has chats', async () => {
    const pending = deferred<ChatHistoryResponse>();
    getChatHistory.mockReturnValue(pending.promise);

    const first = state().loadChatHistory(1, 20);
    await state().loadChatHistory(1, 20);
    pending.resolve(pageOf([chat('a')]));
    await first;
    await state().loadChatHistory(1, 20);

    expect(getChatHistory).toHaveBeenCalledTimes(1);
  });

  it('keeps the error for a retry button, and a retry that works clears it', async () => {
    getChatHistory.mockRejectedValueOnce(new Error('offline'));

    await state().loadChatHistory(1, 20);

    expect(state().chatHistoryError).toBe('offline');
    expect(state().chatHistoryLoading).toBe(false);
    expect(ids()).toEqual([]);

    getChatHistory.mockResolvedValueOnce(pageOf([chat('a')]));
    await state().loadChatHistory(1, 20);

    expect(state().chatHistoryError).toBeNull();
    expect(ids()).toEqual(['a']);
  });
});

describe('a newer history request replaces an older one', () => {
  function startOlderAndNewerRequest() {
    const older = deferred<ChatHistoryResponse>();
    const newer = deferred<ChatHistoryResponse>();
    getChatHistory.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    const olderLoad = state().loadChatHistory(1, 20);
    state().setChatHistorySearchKeyword('plan');
    return { older, newer, olderLoad };
  }

  it('drops the older result when it arrives after the newer one', async () => {
    const { older, newer, olderLoad } = startOlderAndNewerRequest();

    newer.resolve(pageOf([chat('plan-1')], { total: 1 }));
    await settle();
    older.resolve(pageOf([chat('old-1'), chat('old-2')], { total: 2 }));
    await olderLoad;

    expect(ids()).toEqual(['plan-1']);
    expect(state().chatHistoryPagination?.total).toBe(1);
    expect(state().chatHistoryLoading).toBe(false);
  });

  it('drops the older result even when it arrives first, and keeps waiting for the newer one', async () => {
    const { older, newer, olderLoad } = startOlderAndNewerRequest();

    older.resolve(pageOf([chat('old-1')]));
    await olderLoad;

    expect(ids()).toEqual([]);
    expect(state().chatHistoryLoading).toBe(true);

    newer.resolve(pageOf([chat('plan-1')]));
    await settle();

    expect(ids()).toEqual(['plan-1']);
    expect(state().chatHistoryLoading).toBe(false);
  });

  it('does not show an error for an older request that fails after the newer one worked', async () => {
    const { older, newer, olderLoad } = startOlderAndNewerRequest();

    newer.resolve(pageOf([chat('plan-1')]));
    await settle();
    older.reject(new Error('timed out'));
    await olderLoad;

    expect(state().chatHistoryError).toBeNull();
    expect(ids()).toEqual(['plan-1']);
  });

  it('applies to a source filter change as well', async () => {
    const older = deferred<ChatHistoryResponse>();
    const newer = deferred<ChatHistoryResponse>();
    getChatHistory.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    const olderLoad = state().loadChatHistory(1, 20);
    state().setChatHistorySourceFilter('cli');

    newer.resolve(pageOf([chat('cli-1', 'cli')]));
    await settle();
    older.resolve(pageOf([chat('web-1')]));
    await olderLoad;

    expect(ids()).toEqual(['cli-1']);
    expect(getChatHistory).toHaveBeenLastCalledWith(1, 20, 'cli', undefined, undefined);
  });
});

describe('loadMoreChatHistory', () => {
  const seedFirstPage = (...chats: ChatItem[]) =>
    useChatStore.setState({
      chatHistoryItems: chats,
      chatHistoryPagination: pagination({ page: 1, page_size: 20, has_next: true }),
    });

  it('adds the next page after what is listed', async () => {
    seedFirstPage(chat('a'), chat('b'));
    getChatHistory.mockResolvedValue(pageOf([chat('c'), chat('d')], { page: 2, has_next: false }));

    await state().loadMoreChatHistory();

    expect(getChatHistory).toHaveBeenCalledExactlyOnceWith(2, 20, undefined, undefined, undefined);
    expect(ids()).toEqual(['a', 'b', 'c', 'd']);
    expect(state().chatHistoryPagination?.page).toBe(2);
    expect(state().chatHistoryLoading).toBe(false);
  });

  it('does not repeat a chat that two pages both carry', async () => {
    seedFirstPage(chat('a'), chat('b'));
    getChatHistory.mockResolvedValue(pageOf([chat('b'), chat('c')], { page: 2 }));

    await state().loadMoreChatHistory();

    expect(ids()).toEqual(['a', 'b', 'c']);
  });

  it('asks for nothing when there is no next page or a load is already running', async () => {
    useChatStore.setState({ chatHistoryItems: [chat('a')], chatHistoryPagination: pagination({ has_next: false }) });
    await state().loadMoreChatHistory();

    seedFirstPage(chat('a'));
    useChatStore.setState({ chatHistoryLoading: true });
    await state().loadMoreChatHistory();

    expect(getChatHistory).not.toHaveBeenCalled();
  });

  it('stops loading and keeps the list when the page cannot be fetched', async () => {
    seedFirstPage(chat('a'));
    getChatHistory.mockRejectedValue(new Error('offline'));

    await state().loadMoreChatHistory();

    expect(ids()).toEqual(['a']);
    expect(state().chatHistoryLoading).toBe(false);
  });

  it('adds the page to the list as it is when the page arrives, not as it was when asked for', async () => {
    seedFirstPage(chat('a'), chat('b'));
    const pending = deferred<ChatHistoryResponse>();
    getChatHistory.mockReturnValue(pending.promise);
    const loadMore = state().loadMoreChatHistory();

    useChatStore.setState({ chatHistoryItems: [chat('new'), ...state().chatHistoryItems] });
    pending.resolve(pageOf([chat('c')], { page: 2 }));
    await loadMore;

    expect(ids()).toEqual(['new', 'a', 'b', 'c']);
  });

  it('drops a page that was asked for under a filter the list no longer has', async () => {
    seedFirstPage(chat('a'), chat('b'));
    const latePage = deferred<ChatHistoryResponse>();
    const filtered = deferred<ChatHistoryResponse>();
    getChatHistory.mockReturnValueOnce(latePage.promise).mockReturnValueOnce(filtered.promise);
    const loadMore = state().loadMoreChatHistory();
    state().setChatHistorySourceFilter('cli');

    filtered.resolve(pageOf([chat('cli-1', 'cli')]));
    await settle();
    latePage.resolve(pageOf([chat('c')], { page: 2 }));
    await loadMore;

    expect(ids()).toEqual(['cli-1']);
    expect(state().chatHistoryPagination?.page).toBe(1);
    expect(state().chatHistoryLoading).toBe(false);
  });

  it("does not end the newer request's loading when a page asked for earlier fails", async () => {
    seedFirstPage(chat('a'), chat('b'));
    const latePage = deferred<ChatHistoryResponse>();
    const filtered = deferred<ChatHistoryResponse>();
    getChatHistory.mockReturnValueOnce(latePage.promise).mockReturnValueOnce(filtered.promise);
    const loadMore = state().loadMoreChatHistory();
    state().setChatHistorySourceFilter('cli');

    latePage.reject(new Error('timed out'));
    await loadMore;

    expect(state().chatHistoryLoading).toBe(true);

    filtered.resolve(pageOf([chat('cli-1', 'cli')]));
    await settle();

    expect(ids()).toEqual(['cli-1']);
    expect(state().chatHistoryLoading).toBe(false);
  });
});
