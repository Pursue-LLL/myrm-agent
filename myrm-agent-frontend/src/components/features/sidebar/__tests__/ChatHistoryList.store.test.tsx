import { act, render } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatHistoryResponse, ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

import ChatHistoryList from '../ChatHistoryList';

const kit = vi.hoisted(() => ({
  listRenders: 0,
  getChatHistory: vi.fn<(...args: unknown[]) => Promise<ChatHistoryResponse>>(),
}));

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  getChatHistory: kit.getChatHistory,
}));

vi.mock('next/link', () => ({
  default: ({ children, ...props }: ComponentProps<'a'>) => <a {...props}>{children}</a>,
}));
vi.mock('../ProjectBar', () => ({ default: () => null }));
vi.mock('../ProjectMilestonePanel', () => ({ default: () => null }));
vi.mock('../ChatHistoryDialogs', () => ({ ChatHistoryDialogs: () => null }));
/** Rendered once per render of the list, so its count is the list's. */
vi.mock('../ChatHistoryToolbar', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../ChatHistoryToolbar')>();
  return {
    ...actual,
    ChatHistoryToolbar: (props: ComponentProps<typeof actual.ChatHistoryToolbar>) => {
      kit.listRenders += 1;
      return <actual.ChatHistoryToolbar {...props} />;
    },
  };
});

const makeChat = (id: string): ChatItem => ({
  id,
  title: `Title ${id}`,
  firstMessage: 'first',
  lastMessage: `Last ${id}`,
  updatedAt: new Date(),
  createdAt: new Date(),
  actionMode: 'agent',
  source: 'web',
});

const items = [makeChat('a'), makeChat('b')];
const realLoadChatHistory = useChatStore.getState().loadChatHistory;

class IdleIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

async function renderSettledList() {
  render(<ChatHistoryList isExpanded />);
  await act(async () => undefined);
  const settled = kit.listRenders;
  return () => kit.listRenders - settled;
}

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', IdleIntersectionObserver);
  kit.listRenders = 0;
  kit.getChatHistory.mockReset();
  useProjectStore.setState({ activeFilter: undefined });
  useChatStore.setState({
    chatHistoryItems: items,
    chatHistoryPagination: null,
    chatHistoryLoading: false,
    chatHistoryError: null,
    chatHistorySourceFilter: null,
    chatHistorySearchKeyword: '',
    chatHistoryAvailableSources: ['web'],
    sessionStatuses: {},
    chatId: undefined,
    loading: false,
    inputMessage: '',
    loadChatHistory: realLoadChatHistory,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChatHistoryList re-rendering', () => {
  beforeEach(() => {
    // The list reloads the history when it mounts; this reload puts the seeded items in place.
    useChatStore.setState({
      loadChatHistory: vi.fn(async () => {
        useChatStore.setState({ chatHistoryItems: items, chatHistoryLoading: false, chatHistoryError: null });
      }),
    });
  });

  it('stays put while the user types or a reply streams in, none of which it shows', async () => {
    const rendersSince = await renderSettledList();

    // One update per act(), like keystrokes and stream chunks that arrive in separate frames.
    for (let keystroke = 1; keystroke <= 25; keystroke += 1) {
      act(() => useChatStore.setState({ inputMessage: 'x'.repeat(keystroke) }));
    }
    for (let chunk = 1; chunk <= 25; chunk += 1) {
      act(() => useChatStore.setState({ messages: [] }));
    }

    expect(rendersSince()).toBe(0);
  });

  it('redraws when the chat that is open changes', async () => {
    const rendersSince = await renderSettledList();

    act(() => useChatStore.setState({ chatId: 'b' }));

    expect(rendersSince()).toBeGreaterThan(0);
  });

  it('redraws when a chat starts or stops generating', async () => {
    const rendersSince = await renderSettledList();

    act(() => useChatStore.setState({ sessionStatuses: { a: 'generating' } }));

    expect(rendersSince()).toBeGreaterThan(0);
  });

  it('redraws when the history changes', async () => {
    const rendersSince = await renderSettledList();

    act(() => useChatStore.setState({ chatHistoryItems: [makeChat('new'), ...items] }));

    expect(rendersSince()).toBeGreaterThan(0);
  });
});

describe('ChatHistoryList loading', () => {
  const pageOfItems = (): ChatHistoryResponse => ({
    items,
    pagination: { page: 1, page_size: 20, total: 2, total_pages: 1, has_next: false, has_prev: false },
  });
  const flush = () => act(async () => undefined);

  beforeEach(() => {
    useChatStore.setState({ chatHistoryItems: [] });
    kit.getChatHistory.mockResolvedValue(pageOfItems());
  });

  it('asks the server once when the sidebar opens with nothing listed', async () => {
    render(<ChatHistoryList isExpanded />);
    await flush();

    expect(kit.getChatHistory).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().chatHistoryItems.map((item) => item.id)).toEqual(['a', 'b']);
  });

  it('does not ask again when a sidebar that loaded while collapsed is expanded', async () => {
    const { rerender } = render(<ChatHistoryList isExpanded={false} />);
    await flush();

    rerender(<ChatHistoryList isExpanded />);
    await flush();

    expect(kit.getChatHistory).toHaveBeenCalledTimes(1);
  });

  it('starts over with the new project when the project filter changes', async () => {
    render(<ChatHistoryList isExpanded />);
    await flush();
    kit.getChatHistory.mockClear();

    act(() => useProjectStore.setState({ activeFilter: 'project-1' }));
    await flush();

    expect(kit.getChatHistory).toHaveBeenCalledExactlyOnceWith(1, 20, undefined, 'project-1', undefined);
  });
});
