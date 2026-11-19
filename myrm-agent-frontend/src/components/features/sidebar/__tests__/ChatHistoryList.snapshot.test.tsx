import { act, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatHistoryResponse, ChatItem } from '@/services/chat';
import { encodeChatHistory } from '@/store/first-screen/chatHistorySection';
import { flushSnapshot, resetSnapshotForTests, writeSnapshotSection } from '@/store/first-screen/envelope';
import { resetSeedingForTests } from '@/store/first-screen/restore';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';
import { deferred } from '@/test-utils/deferred';

import ChatHistoryList from '../ChatHistoryList';

const kit = vi.hoisted(() => ({
  snapshotEnabled: true,
  getChatHistory: vi.fn<(...args: unknown[]) => Promise<ChatHistoryResponse>>(),
}));

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  getChatHistory: kit.getChatHistory,
}));
vi.mock('@/store/first-screen/gate', () => ({ isFirstScreenSnapshotEnabled: () => kit.snapshotEnabled }));
vi.mock('next/link', () => ({
  default: ({ children, ...props }: ComponentProps<'a'>) => <a {...props}>{children}</a>,
}));
vi.mock('../ProjectBar', () => ({ default: () => null }));
vi.mock('../ProjectMilestonePanel', () => ({ default: () => null }));
vi.mock('../ChatHistoryDialogs', () => ({ ChatHistoryDialogs: () => null }));

const makeChat = (id: string, title: string, lastMessage = ''): ChatItem => ({
  id,
  title,
  firstMessage: '',
  lastMessage,
  updatedAt: new Date(),
  createdAt: new Date(),
  actionMode: 'agent',
  source: 'web',
});

const storedList = [makeChat('old-a', 'Stored chat A', 'Stored preview A'), makeChat('old-b', 'Stored chat B')];
const freshPage = (): ChatHistoryResponse => ({
  items: [makeChat('fresh', 'Fresh chat')],
  pagination: { page: 1, page_size: 20, total: 1, total_pages: 1, has_next: false, has_prev: false },
});

class IdleIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const storeSnapshot = (filterKey = 'all') => {
  writeSnapshotSection('chatHistory', encodeChatHistory(filterKey, storedList));
  flushSnapshot();
};
const flush = () => act(async () => undefined);

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', IdleIntersectionObserver);
  window.localStorage.clear();
  resetSnapshotForTests();
  resetSeedingForTests();
  kit.snapshotEnabled = true;
  kit.getChatHistory.mockReset();
  useProjectStore.setState({ activeFilter: undefined });
  useChatStore.setState({
    chatHistoryItems: [],
    chatHistoryPagination: null,
    chatHistoryLoading: false,
    chatHistoryError: null,
    chatHistorySourceFilter: null,
    chatHistorySearchKeyword: '',
    chatHistoryAvailableSources: [],
    sessionStatuses: {},
    chatId: undefined,
    loading: false,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetSnapshotForTests();
});

describe('ChatHistoryList first-screen snapshot', () => {
  it('draws the stored list while the server has not answered and swaps in the first page when it arrives', async () => {
    storeSnapshot();
    const answer = deferred<ChatHistoryResponse>();
    kit.getChatHistory.mockReturnValue(answer.promise);

    render(<ChatHistoryList isExpanded />);
    await flush();

    expect(screen.getByText('Stored chat A')).toBeInTheDocument();
    expect(screen.getByText('Stored chat B')).toBeInTheDocument();
    expect(screen.getByText('Stored preview A')).toBeInTheDocument();
    expect(screen.getByText('common.loading')).toBeInTheDocument();
    expect(kit.getChatHistory).toHaveBeenCalledExactlyOnceWith(1, 20, undefined, undefined, undefined);

    await act(async () => answer.resolve(freshPage()));

    expect(screen.getByText('Fresh chat')).toBeInTheDocument();
    expect(screen.queryByText('Stored chat A')).not.toBeInTheDocument();
    expect(screen.queryByText('common.loading')).not.toBeInTheDocument();
    expect(useChatStore.getState().chatHistoryPagination?.total).toBe(1);
  });

  it('keeps the stored list on screen when the refresh fails, instead of an error panel', async () => {
    storeSnapshot();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    kit.getChatHistory.mockRejectedValue(new Error('backend unreachable'));

    render(<ChatHistoryList isExpanded />);
    await flush();

    expect(screen.getByText('Stored chat A')).toBeInTheDocument();
    expect(screen.queryByText('common.loadHistoryError')).not.toBeInTheDocument();
    expect(useChatStore.getState().chatHistoryError).toBe('backend unreachable');
  });

  it('shows the loading rows and no chats when nothing was stored', async () => {
    const answer = deferred<ChatHistoryResponse>();
    kit.getChatHistory.mockReturnValue(answer.promise);

    const { container } = render(<ChatHistoryList isExpanded />);
    await flush();

    expect(screen.queryByText('Stored chat A')).not.toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(3);
  });

  it('starts from an empty list when the feature is off, whatever is stored', async () => {
    storeSnapshot();
    kit.snapshotEnabled = false;
    kit.getChatHistory.mockReturnValue(deferred<ChatHistoryResponse>().promise);

    render(<ChatHistoryList isExpanded />);
    await flush();

    expect(screen.queryByText('Stored chat A')).not.toBeInTheDocument();
  });

  it('ignores a stored list that belongs to another project filter', async () => {
    storeSnapshot('project:other');
    kit.getChatHistory.mockReturnValue(deferred<ChatHistoryResponse>().promise);

    render(<ChatHistoryList isExpanded />);
    await flush();

    expect(screen.queryByText('Stored chat A')).not.toBeInTheDocument();
  });

  it('puts the stored list up for the first mount only', async () => {
    storeSnapshot();
    kit.getChatHistory.mockReturnValue(deferred<ChatHistoryResponse>().promise);
    const first = render(<ChatHistoryList isExpanded />);
    await flush();
    expect(screen.getByText('Stored chat A')).toBeInTheDocument();
    first.unmount();

    render(<ChatHistoryList isExpanded />);
    await flush();

    expect(screen.queryByText('Stored chat A')).not.toBeInTheDocument();
  });

  it('drops the stored list for the new project when the filter changes, instead of mixing the two', async () => {
    storeSnapshot();
    kit.getChatHistory.mockReturnValue(deferred<ChatHistoryResponse>().promise);
    render(<ChatHistoryList isExpanded />);
    await flush();
    kit.getChatHistory.mockClear();

    act(() => useProjectStore.setState({ activeFilter: 'project-1' }));
    await flush();

    expect(screen.queryByText('Stored chat A')).not.toBeInTheDocument();
    expect(kit.getChatHistory).toHaveBeenCalledExactlyOnceWith(1, 20, undefined, 'project-1', undefined);
  });
});
