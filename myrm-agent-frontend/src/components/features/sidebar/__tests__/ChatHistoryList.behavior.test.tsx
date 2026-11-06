import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

type StoreState = ReturnType<typeof useChatStore.getState>;

const captured = vi.hoisted(() => ({
  batchBar: [] as Record<string, unknown>[],
  confirm: [] as Record<string, unknown>[],
  cron: [] as Record<string, unknown>[],
  handoff: [] as Record<string, unknown>[],
  share: [] as Record<string, unknown>[],
  capture: [] as Record<string, unknown>[],
}));
const lastOf = (list: Record<string, unknown>[]) => list[list.length - 1];

vi.mock('next/link', () => ({
  default: ({ children, ...props }: ComponentProps<'a'>) => <a {...props}>{children}</a>,
}));
vi.mock('hugeicons-react', () => ({ AiNetworkIcon: () => <span data-testid="ai-network-icon" /> }));
vi.mock('@/components/features/settings/sections/integration/channels/ChannelIcon', () => ({
  default: ({ channelId }: { channelId: string }) => <span data-testid="channel-icon" data-channel={channelId} />,
}));
vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
  }: {
    children: ReactNode;
    onClick?: () => void;
    disabled?: boolean;
  }) => (
    <button type="button" role="menuitem" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuSub: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: { children: ReactNode }) => <div role="menuitem">{children}</div>,
  DropdownMenuSubContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('../ProjectBar', () => ({
  default: ({ isMobile }: { isMobile: boolean }) => <div data-testid="project-bar" data-mobile={String(isMobile)} />,
}));
vi.mock('../ProjectMilestonePanel', () => ({ default: () => <div data-testid="milestone-panel" /> }));
vi.mock('../BatchOperationBar', () => ({
  default: (props: {
    selectedCount: number;
    totalCount: number;
    isMobile: boolean;
    onSelectAll: () => void;
    onDeselectAll: () => void;
    onDelete: () => void;
    onExit: () => void;
  }) => {
    captured.batchBar.push(props);
    return (
      <div
        data-testid="batch-bar"
        data-selected={props.selectedCount}
        data-total={props.totalCount}
        data-mobile={String(props.isMobile)}
      >
        <button onClick={props.onSelectAll}>select-all</button>
        <button onClick={props.onDeselectAll}>deselect-all</button>
        <button onClick={props.onDelete}>delete-selected</button>
        <button onClick={props.onExit}>exit-batch</button>
      </div>
    );
  },
}));
vi.mock('@/components/features/app-shell/confirm-dialog', () => ({
  ConfirmDialog: (props: { open: boolean; title: string; onOpenChange: (open: boolean) => void }) => {
    captured.confirm.push(props);
    return <div data-testid={`confirm:${props.title}`} data-open={String(props.open)} />;
  },
}));
vi.mock('@/components/features/cron/CronJobCreateDialog', () => ({
  default: (props: Record<string, unknown>) => {
    captured.cron.push(props);
    return <div data-testid="cron-dialog" data-open={String(props.open)} />;
  },
}));
vi.mock('../HandoffDialog', () => ({
  HandoffDialog: (props: Record<string, unknown>) => {
    captured.handoff.push(props);
    return <div data-testid="handoff-dialog" data-open={String(props.open)} />;
  },
}));
vi.mock('../ShareConversationDialog', () => ({
  ShareConversationDialog: (props: Record<string, unknown>) => {
    captured.share.push(props);
    return <div data-testid="share-dialog" data-open={String(props.open)} />;
  },
}));
vi.mock('../CaptureEvalCaseDialog', () => ({
  CaptureEvalCaseDialog: (props: Record<string, unknown>) => {
    captured.capture.push(props);
    return <div data-testid="capture-dialog" data-open={String(props.open)} />;
  },
}));

import ChatHistoryList from '../ChatHistoryList';

const DAY_MS = 86_400_000;
const GROUPS_STORAGE_KEY = 'myrm:sidebar:collapsed-groups';

const makeChat = (id: string, overrides: Partial<ChatItem> = {}): ChatItem => ({
  id,
  title: `Title ${id}`,
  firstMessage: 'first',
  lastMessage: `Last ${id}`,
  updatedAt: new Date(),
  createdAt: new Date(),
  actionMode: 'agent',
  source: 'web',
  ...overrides,
});

const daysAgo = (days: number) => new Date(Date.now() - days * DAY_MS);

interface IntersectionRecord {
  callback: IntersectionObserverCallback;
  observed: Element[];
  disconnected: boolean;
}
const observers: IntersectionRecord[] = [];
class FakeIntersectionObserver {
  private readonly record: IntersectionRecord;
  constructor(callback: IntersectionObserverCallback) {
    this.record = { callback, observed: [], disconnected: false };
    observers.push(this.record);
  }
  observe(element: Element) {
    this.record.observed.push(element);
  }
  unobserve() {}
  disconnect() {
    this.record.disconnected = true;
  }
}

const storeActions = {
  loadMoreChatHistory: vi.fn(),
  setChatHistorySourceFilter: vi.fn(),
  setChatHistorySearchKeyword: vi.fn(),
  reorderPinnedChats: vi.fn(),
};

/** The list clears the history on mount and reloads it, so the reload is what puts the seeded state in place. */
function seed(state: Partial<StoreState> = {}) {
  const loadChatHistory = vi.fn(async () => {
    useChatStore.setState({ chatHistoryLoading: false, chatHistoryError: null, ...state });
  });
  useChatStore.setState({
    chatHistoryItems: [],
    chatHistoryPagination: null,
    chatHistoryLoading: false,
    chatHistoryError: null,
    chatHistorySourceFilter: null,
    chatHistorySearchKeyword: '',
    chatHistoryAvailableSources: ['web'],
    sessionStatuses: {},
    chatId: undefined,
    loading: false,
    loadChatHistory,
    ...storeActions,
  });
  return loadChatHistory;
}

async function renderList(props: Partial<ComponentProps<typeof ChatHistoryList>> = {}) {
  const view = render(<ChatHistoryList isExpanded {...props} />);
  await act(async () => {});
  return view;
}

const rowOf = (title: string) => {
  const link = screen.getByRole('link', { name: new RegExp(title) });
  const row = link.closest('div.relative');
  if (!(row instanceof HTMLElement)) {
    throw new Error(`row of ${title} not found`);
  }
  return row;
};

/** The grid wrapper that animates a date group's rows open and closed. */
const groupBodyOf = (title: string) => {
  const body = rowOf(title).closest('div.grid');
  if (!(body instanceof HTMLElement)) {
    throw new Error(`date group of ${title} not found`);
  }
  return body;
};

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
  vi.clearAllMocks();
  observers.length = 0;
  for (const list of Object.values(captured)) {
    list.length = 0;
  }
  localStorage.clear();
  useProjectStore.setState({ projects: [], activeFilter: undefined });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('ChatHistoryList loading', () => {
  it('renders nothing while collapsed', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });

    const { container } = await renderList({ isExpanded: false });

    expect(container).toBeEmptyDOMElement();
  });

  it('loads the first page on mount', async () => {
    const load = seed({ chatHistoryItems: [makeChat('a')] });

    await renderList();

    expect(load).toHaveBeenCalledWith(1, 20);
    expect(screen.getByText('Title a')).toBeInTheDocument();
  });

  it('shows placeholders while the first page loads', async () => {
    seed({ chatHistoryItems: [], chatHistoryLoading: true });

    const { container } = await renderList();

    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(3);
  });

  it('shows the error and retries from the first page', async () => {
    const load = seed({ chatHistoryItems: [], chatHistoryError: 'boom' });

    await renderList();
    expect(screen.getByText('common.loadHistoryError')).toBeInTheDocument();
    load.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));

    expect(load).toHaveBeenCalledWith(1, 20);
  });

  it('shows that more chats are loading below the existing ones', async () => {
    seed({ chatHistoryItems: [makeChat('a')], chatHistoryLoading: true });

    await renderList();

    expect(screen.getByText('common.loading')).toBeInTheDocument();
    expect(screen.getByText('Title a')).toBeInTheDocument();
  });
});

describe('ChatHistoryList infinite scroll', () => {
  const trigger = (isIntersecting: boolean) => {
    const live = observers.filter((record) => !record.disconnected).at(-1);
    if (!live) {
      throw new Error('no live observer');
    }
    act(() => live.callback([{ isIntersecting } as IntersectionObserverEntry], {} as IntersectionObserver));
  };

  it('watches the sentinel under the list and loads more when it scrolls into view', async () => {
    seed({
      chatHistoryItems: [makeChat('a')],
      chatHistoryPagination: { has_next: true } as StoreState['chatHistoryPagination'],
    });
    const { container } = await renderList();

    const live = observers.filter((record) => !record.disconnected).at(-1);
    expect(live?.observed[0]).toBe(container.querySelector('div.h-px'));

    trigger(false);
    expect(storeActions.loadMoreChatHistory).not.toHaveBeenCalled();
    trigger(true);
    expect(storeActions.loadMoreChatHistory).toHaveBeenCalledTimes(1);
  });

  it('stops asking when there is no next page', async () => {
    seed({
      chatHistoryItems: [makeChat('a')],
      chatHistoryPagination: { has_next: false } as StoreState['chatHistoryPagination'],
    });
    await renderList();

    trigger(true);

    expect(storeActions.loadMoreChatHistory).not.toHaveBeenCalled();
  });

  it('does not ask again while a page is loading', async () => {
    seed({
      chatHistoryItems: [makeChat('a')],
      chatHistoryLoading: true,
      chatHistoryPagination: { has_next: true } as StoreState['chatHistoryPagination'],
    });
    await renderList();

    trigger(true);

    expect(storeActions.loadMoreChatHistory).not.toHaveBeenCalled();
  });
});

describe('ChatHistoryList source filter', () => {
  it('shows no chips for a single source', async () => {
    seed({ chatHistoryItems: [makeChat('a')], chatHistoryAvailableSources: ['web'] });

    await renderList();

    expect(screen.queryByTitle('web')).toBeNull();
  });

  it('lets the viewer pick a source and click it again to clear it', async () => {
    seed({ chatHistoryItems: [makeChat('a')], chatHistoryAvailableSources: ['web', 'telegram'] });
    await renderList();

    fireEvent.click(screen.getByTitle('telegram'));
    expect(storeActions.setChatHistorySourceFilter).toHaveBeenLastCalledWith('telegram');
  });

  it('highlights the active source and clears it on a second click', async () => {
    seed({
      chatHistoryItems: [makeChat('a')],
      chatHistoryAvailableSources: ['web', 'telegram'],
      chatHistorySourceFilter: 'telegram',
    });
    await renderList();

    expect(screen.getByTitle('telegram').className).toContain('bg-primary/15');
    expect(screen.getByTitle('web').className).toContain('opacity-50');
    fireEvent.click(screen.getByTitle('telegram'));

    expect(storeActions.setChatHistorySourceFilter).toHaveBeenLastCalledWith(null);
  });

  it('keeps the chips while a filter hides every other source', async () => {
    seed({
      chatHistoryItems: [makeChat('a')],
      chatHistoryAvailableSources: ['telegram'],
      chatHistorySourceFilter: 'telegram',
    });

    await renderList();

    expect(screen.getByTitle('telegram')).toBeInTheDocument();
  });
});

describe('ChatHistoryList search', () => {
  const openSearch = () => {
    fireEvent.click(screen.getByRole('button', { name: 'common.search' }));
    return screen.getByPlaceholderText('common.search');
  };

  it('opens a search field and focuses it', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    await renderList();
    expect(screen.queryByPlaceholderText('common.search')).toBeNull();

    const input = openSearch();

    await waitFor(() => expect(input).toHaveFocus());
  });

  it('echoes typing at once and applies the keyword after the pause', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    await renderList();
    const input = openSearch();
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });

    fireEvent.change(input, { target: { value: 'a' } });
    fireEvent.change(input, { target: { value: 'ab' } });

    expect(input).toHaveValue('ab');
    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(storeActions.setChatHistorySearchKeyword).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(storeActions.setChatHistorySearchKeyword).toHaveBeenCalledTimes(1);
    expect(storeActions.setChatHistorySearchKeyword).toHaveBeenCalledWith('ab');
  });

  it('clears and closes on Escape', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    await renderList();
    const input = openSearch();
    fireEvent.change(input, { target: { value: 'ab' } });

    fireEvent.keyDown(input, { key: 'Escape' });

    expect(storeActions.setChatHistorySearchKeyword).toHaveBeenCalledWith('');
    expect(screen.queryByPlaceholderText('common.search')).toBeNull();
  });

  it('clears and closes from the clear button next to the field', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    const { container } = await renderList();
    const input = openSearch();
    expect(container.querySelector('input + button')).toBeNull();
    fireEvent.change(input, { target: { value: 'ab' } });

    fireEvent.click(container.querySelector('input + button') as HTMLButtonElement);

    expect(storeActions.setChatHistorySearchKeyword).toHaveBeenCalledWith('');
    expect(screen.queryByPlaceholderText('common.search')).toBeNull();
  });

  it('clears a typed keyword when the toggle closes the field', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    await renderList();
    const input = openSearch();
    fireEvent.change(input, { target: { value: 'ab' } });

    fireEvent.click(screen.getByRole('button', { name: 'common.search' }));

    expect(storeActions.setChatHistorySearchKeyword).toHaveBeenCalledWith('');
    expect(screen.queryByPlaceholderText('common.search')).toBeNull();
  });

  it('closes an empty field without touching the stored keyword', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    await renderList();
    openSearch();

    fireEvent.click(screen.getByRole('button', { name: 'common.search' }));

    expect(screen.queryByPlaceholderText('common.search')).toBeNull();
    expect(storeActions.setChatHistorySearchKeyword).not.toHaveBeenCalled();
  });

  it('shows a spinner in the field while a search is loading', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    const { container } = await renderList();
    const input = openSearch();
    expect(container.querySelector('.animate-spin')).toBeNull();

    fireEvent.change(input, { target: { value: 'ab' } });
    act(() => useChatStore.setState({ chatHistoryLoading: true }));

    expect(container.querySelector('.animate-spin')).not.toBeNull();
  });

  it('highlights the search toggle while a keyword is applied', async () => {
    seed({ chatHistoryItems: [makeChat('a')], chatHistorySearchKeyword: 'ab' });

    await renderList();

    expect(screen.getByRole('button', { name: 'common.search' }).className).toContain('bg-primary/15');
  });
});

describe('ChatHistoryList batch mode', () => {
  const twoChats = [makeChat('a'), makeChat('b')];

  it('offers batch selection only when there are several unpinned chats', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    const single = await renderList();
    expect(screen.queryByRole('button', { name: 'chat.batch.enter' })).toBeNull();
    single.unmount();

    seed({ chatHistoryItems: [makeChat('a'), makeChat('b', { isPinned: true, pinOrder: 0 })] });
    const pinnedOnly = await renderList();
    expect(screen.queryByRole('button', { name: 'chat.batch.enter' })).toBeNull();
    pinnedOnly.unmount();

    seed({ chatHistoryItems: twoChats });
    await renderList();
    expect(screen.getByRole('button', { name: 'chat.batch.enter' })).toBeInTheDocument();
  });

  it('enters batch mode with an empty selection over the unpinned chats', async () => {
    seed({ chatHistoryItems: [...twoChats, makeChat('p', { isPinned: true, pinOrder: 0 })] });
    await renderList({ isMobile: true });

    fireEvent.click(screen.getByRole('button', { name: 'chat.batch.enter' }));

    const bar = screen.getByTestId('batch-bar');
    expect(bar).toHaveAttribute('data-selected', '0');
    expect(bar).toHaveAttribute('data-total', '2');
    expect(bar).toHaveAttribute('data-mobile', 'true');
    expect(screen.queryByRole('button', { name: 'chat.batch.enter' })).toBeNull();
  });

  it('selects rows by clicking them and counts the selection', async () => {
    seed({ chatHistoryItems: twoChats });
    await renderList();
    fireEvent.click(screen.getByRole('button', { name: 'chat.batch.enter' }));

    fireEvent.click(screen.getByRole('link', { name: /Title a/ }));
    expect(screen.getByTestId('batch-bar')).toHaveAttribute('data-selected', '1');

    fireEvent.click(screen.getByRole('link', { name: /Title b/ }));
    expect(screen.getByTestId('batch-bar')).toHaveAttribute('data-selected', '2');

    fireEvent.click(screen.getByRole('link', { name: /Title a/ }));
    expect(screen.getByTestId('batch-bar')).toHaveAttribute('data-selected', '1');
  });

  it('selects every unpinned chat and deselects them again', async () => {
    seed({ chatHistoryItems: [...twoChats, makeChat('p', { isPinned: true, pinOrder: 0 })] });
    await renderList();
    fireEvent.click(screen.getByRole('button', { name: 'chat.batch.enter' }));

    fireEvent.click(screen.getByText('select-all'));
    expect(screen.getByTestId('batch-bar')).toHaveAttribute('data-selected', '2');

    fireEvent.click(screen.getByText('deselect-all'));
    expect(screen.getByTestId('batch-bar')).toHaveAttribute('data-selected', '0');
  });

  it('leaves batch mode from the bar and from the Escape key', async () => {
    seed({ chatHistoryItems: twoChats });
    await renderList();

    fireEvent.click(screen.getByRole('button', { name: 'chat.batch.enter' }));
    fireEvent.click(screen.getByText('exit-batch'));
    expect(screen.queryByTestId('batch-bar')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'chat.batch.enter' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('batch-bar')).toBeNull();
  });

  it('asks before deleting a selection and ignores an empty one', async () => {
    seed({ chatHistoryItems: twoChats });
    await renderList();
    fireEvent.click(screen.getByRole('button', { name: /chat.batch.enter/ }));

    fireEvent.click(screen.getByText('delete-selected'));
    expect(screen.getByTestId('confirm:chat.batch.confirmTitle')).toHaveAttribute('data-open', 'false');

    fireEvent.click(screen.getByRole('link', { name: /Title a/ }));
    fireEvent.click(screen.getByText('delete-selected'));

    expect(screen.getByTestId('confirm:chat.batch.confirmTitle')).toHaveAttribute('data-open', 'true');
    expect(lastOf(captured.confirm.filter((props) => props.title === 'chat.batch.confirmTitle'))).toMatchObject({
      variant: 'destructive',
    });
  });
});

describe('ChatHistoryList grouping', () => {
  it('pins chats on top in pin order, numbered, apart from the dated groups', async () => {
    seed({
      chatHistoryItems: [
        makeChat('late', { isPinned: true, pinOrder: 2 }),
        makeChat('early', { isPinned: true, pinOrder: 1 }),
        makeChat('plain'),
      ],
    });
    const { container } = await renderList();

    expect(screen.getByText('chat.pin.section')).toBeInTheDocument();
    const order = Array.from(container.querySelectorAll('a[href]')).map((link) => link.getAttribute('href'));
    expect(order).toEqual(['/early', '/late', '/plain']);
    expect(Array.from(container.querySelectorAll('kbd')).map((kbd) => kbd.textContent)).toEqual(['1', '2']);
  });

  it('shows no pinned section without pinned chats', async () => {
    seed({ chatHistoryItems: [makeChat('plain')] });

    await renderList();

    expect(screen.queryByText('chat.pin.section')).toBeNull();
  });

  it('groups unpinned chats by date, newest group first, skipping empty ones', async () => {
    seed({
      chatHistoryItems: [
        makeChat('old', { updatedAt: daysAgo(60) }),
        makeChat('now'),
        makeChat('month', { updatedAt: daysAgo(15) }),
      ],
    });

    await renderList();

    const headings = screen
      .getAllByRole('button')
      .map((button) => button.textContent)
      .filter((text) => text?.startsWith('chat.dateGroup.'));
    expect(headings).toEqual(['chat.dateGroup.today', 'chat.dateGroup.prev30days', 'chat.dateGroup.older']);
  });

  it('collapses and expands a group and remembers it', async () => {
    seed({ chatHistoryItems: [makeChat('now')] });
    await renderList();
    const heading = screen.getByRole('button', { name: 'chat.dateGroup.today' });
    expect(groupBodyOf('Title now').style.gridTemplateRows).toBe('1fr');

    fireEvent.click(heading);
    expect(groupBodyOf('Title now').style.gridTemplateRows).toBe('0fr');
    expect(JSON.parse(localStorage.getItem(GROUPS_STORAGE_KEY) ?? '{}')).toEqual({ today: true });

    fireEvent.click(heading);
    expect(groupBodyOf('Title now').style.gridTemplateRows).toBe('1fr');
    expect(JSON.parse(localStorage.getItem(GROUPS_STORAGE_KEY) ?? '{}')).toEqual({ today: false });
  });

  it('starts with the groups the viewer collapsed before', async () => {
    localStorage.setItem(GROUPS_STORAGE_KEY, JSON.stringify({ today: true }));
    seed({ chatHistoryItems: [makeChat('now')] });

    await renderList();

    expect(groupBodyOf('Title now').style.gridTemplateRows).toBe('0fr');
  });
});

describe('ChatHistoryList rows', () => {
  it('marks the open chat and shows which chats are working', async () => {
    seed({
      chatHistoryItems: [makeChat('open'), makeChat('busy'), makeChat('asking'), makeChat('current')],
      sessionStatuses: { busy: 'generating', asking: 'awaiting_approval' },
      chatId: 'current',
      loading: true,
    });

    await renderList({ currentChatId: 'open' });

    expect(screen.getByRole('link', { name: /Title open/ }).className).toContain('brand-selected-surface');
    expect(screen.getByRole('link', { name: /Title busy/ }).className).not.toContain('brand-selected-surface');
    expect(rowOf('Title busy').querySelector('.bg-emerald-500')).not.toBeNull();
    expect(rowOf('Title asking').querySelector('.bg-amber-500')).not.toBeNull();
    expect(rowOf('Title current').querySelector('.bg-emerald-500')).not.toBeNull();
    expect(rowOf('Title open').querySelector('.bg-emerald-500, .bg-amber-500')).toBeNull();
  });

  it('reports a row click so a drawer can close', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    const onItemClick = vi.fn();
    await renderList({ onItemClick });
    const link = screen.getByRole('link', { name: /Title a/ });
    link.addEventListener('click', (event) => event.preventDefault()); // jsdom cannot navigate

    fireEvent.click(link);

    expect(onItemClick).toHaveBeenCalledTimes(1);
  });

  it('keeps rows from being dragged into the composer outside the desktop shell', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });

    await renderList();

    expect(screen.getByRole('link', { name: /Title a/ })).toHaveAttribute('draggable', 'false');
    expect(screen.queryByRole('menuitem', { name: 'chat.openInNewWindow' })).toBeNull();
  });

  it('hands the project bar the phone flag and mounts the milestone panel', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });

    await renderList({ isMobile: true });

    expect(screen.getByTestId('project-bar')).toHaveAttribute('data-mobile', 'true');
    expect(screen.getByTestId('milestone-panel')).toBeInTheDocument();
  });
});

describe('ChatHistoryList dialogs', () => {
  const clickInRow = (title: string, name: string) =>
    fireEvent.click(within(rowOf(title)).getByRole('menuitem', { name }));

  it('mounts every dialog closed', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });

    await renderList();

    expect(screen.getByTestId('confirm:chat.deleteChat.title')).toHaveAttribute('data-open', 'false');
    expect(screen.getByTestId('confirm:chat.batch.confirmTitle')).toHaveAttribute('data-open', 'false');
    expect(screen.getByTestId('cron-dialog')).toHaveAttribute('data-open', 'false');
    expect(screen.getByTestId('share-dialog')).toHaveAttribute('data-open', 'false');
    expect(screen.getByTestId('capture-dialog')).toHaveAttribute('data-open', 'false');
    expect(screen.queryByTestId('handoff-dialog')).toBeNull();
  });

  it('confirms before deleting a chat', async () => {
    seed({ chatHistoryItems: [makeChat('a'), makeChat('b')] });
    await renderList();

    clickInRow('Title b', 'common.delete');

    expect(screen.getByTestId('confirm:chat.deleteChat.title')).toHaveAttribute('data-open', 'true');
    expect(lastOf(captured.confirm.filter((props) => props.title === 'chat.deleteChat.title'))).toMatchObject({
      description: 'chat.deleteChat.description',
      confirmText: 'chat.deleteChat.confirm',
      cancelText: 'chat.deleteChat.cancel',
      loadingText: 'chat.deleteChat.deleting',
      variant: 'destructive',
    });
  });

  it('presets the automation dialog with the chat', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    await renderList();

    clickInRow('Title a', 'chat.createAutomation');

    expect(screen.getByTestId('cron-dialog')).toHaveAttribute('data-open', 'true');
    expect(lastOf(captured.cron)).toMatchObject({ presetChatId: 'a', presetChatTitle: 'Title a' });
  });

  it('mounts the handoff dialog for the chosen chat and its source', async () => {
    seed({ chatHistoryItems: [makeChat('a', { source: 'web' })] });
    await renderList();

    clickInRow('Title a', 'chat.handoff.menuAction');

    expect(screen.getByTestId('handoff-dialog')).toHaveAttribute('data-open', 'true');
    expect(lastOf(captured.handoff)).toMatchObject({ chatId: 'a', chatTitle: 'Title a', currentSource: 'web' });
  });

  it('opens the capture dialog for the chosen chat', async () => {
    seed({ chatHistoryItems: [makeChat('a')] });
    await renderList();

    clickInRow('Title a', 'chat.captureEvalCase.action');

    expect(screen.getByTestId('capture-dialog')).toHaveAttribute('data-open', 'true');
    expect(lastOf(captured.capture)).toMatchObject({ chatId: 'a' });
  });
});
