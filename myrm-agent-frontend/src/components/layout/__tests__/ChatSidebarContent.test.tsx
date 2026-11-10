import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deferred } from '@/test-utils/deferred';
import useChatStore from '@/store/useChatStore';
import { ChatSidebarContent } from '../ChatSidebarContent';
import { kit, resetSidebarKit } from './sidebarKit';

vi.mock('next/navigation', async () => (await import('./sidebarKit')).navigationMock());
vi.mock('next/dynamic', async () => (await import('./sidebarKit')).nextDynamicMock());
vi.mock('@/components/features/app-shell/BrandLogo', async () => (await import('./sidebarKit')).brandLogoMock());
vi.mock('@/components/features/sidebar/SessionImportModal', async () =>
  (await import('./sidebarKit')).importModalMock(),
);
vi.mock('@/components/features/app-shell/search-dialog', async () => (await import('./sidebarKit')).searchDialogMock());
vi.mock('@/components/features/sidebar/ChatHistoryList', async () => (await import('./sidebarKit')).historyListMock());
vi.mock('@/components/features/chat-window/catchup/CatchupInbox', async () =>
  (await import('./sidebarKit')).catchupMock(),
);
vi.mock('@/components/features/extension-slots', async () => (await import('./sidebarKit')).extensionSlotMock());
vi.mock('@/components/features/chat-window/SessionTrashPanel', async () =>
  (await import('./sidebarKit')).trashPanelMock(),
);
vi.mock('@/components/features/workspace-browser/useWorkspaceFiles', async () =>
  (await import('./sidebarKit')).workspaceFilesMock(),
);
vi.mock('@/services/chatTrash', async (importOriginal) => (await import('./sidebarKit')).chatTrashMock(importOriginal));

const handlers = {
  onNewChat: vi.fn<() => void>(),
  onToggleCollapse: vi.fn<() => void>(),
  onMobileItemClick: vi.fn<() => void>(),
};

function renderSidebar(props: { isMobile?: boolean; withItemClick?: boolean } = {}) {
  const { isMobile, withItemClick = true } = props;
  return render(
    <ChatSidebarContent
      onNewChat={handlers.onNewChat}
      onToggleCollapse={handlers.onToggleCollapse}
      isMobile={isMobile}
      onMobileItemClick={withItemClick ? handlers.onMobileItemClick : undefined}
    />,
  );
}

async function settle(): Promise<void> {
  await act(async () => undefined);
}

/** The state of a chat that has a workspace folder, which is what makes the Files tab appear. */
function openAgentChatWithWorkspace(workspaceDir = '/work/alpha'): void {
  useChatStore.setState({ chatId: 'c-1', actionMode: 'agent', workspaceDir });
}

const chatTab = () => screen.getByRole('button', { name: 'sidebar.chatHistory' });
const filesTab = () => screen.getByRole('button', { name: 'sidebar.files' });

beforeEach(() => {
  resetSidebarKit();
  useChatStore.setState({ chatId: undefined, actionMode: 'fast', workspaceDir: null });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ChatSidebarContent header', () => {
  it('takes the user home from the brand', () => {
    renderSidebar();

    fireEvent.click(screen.getByRole('button', { name: /MyrmAgent/ }));

    expect(kit.push).toHaveBeenCalledExactlyOnceWith('/');
  });

  it('collapses from the collapse button', () => {
    renderSidebar();

    fireEvent.click(screen.getByRole('button', { name: 'common.collapseMenu' }));

    expect(handlers.onToggleCollapse).toHaveBeenCalledTimes(1);
  });

  it('shows the catch-up inbox and the extension footer', () => {
    renderSidebar();

    expect(screen.getByTestId('catchup-inbox')).toBeInTheDocument();
    expect(screen.getByTestId('slot:sidebar.footer.action')).toBeInTheDocument();
  });
});

describe('ChatSidebarContent actions', () => {
  it('starts a new chat from the New chat button', () => {
    renderSidebar();

    fireEvent.click(screen.getByRole('button', { name: 'chat.newChat' }));

    expect(handlers.onNewChat).toHaveBeenCalledTimes(1);
  });

  it('opens and closes the session import dialog', () => {
    renderSidebar();
    expect(screen.getByTestId('import-modal')).toHaveAttribute('data-open', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'chat.import.buttonTitle' }));
    expect(screen.getByTestId('import-modal')).toHaveAttribute('data-open', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'close-import' }));
    expect(screen.getByTestId('import-modal')).toHaveAttribute('data-open', 'false');
  });

  it('opens and closes the search dialog from the search field', () => {
    renderSidebar();
    expect(screen.getByTestId('search-dialog')).toHaveAttribute('data-open', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'sidebar.searchPlaceholder' }));
    expect(screen.getByTestId('search-dialog')).toHaveAttribute('data-open', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'close-search' }));
    expect(screen.getByTestId('search-dialog')).toHaveAttribute('data-open', 'false');
  });
});

describe('ChatSidebarContent chat history', () => {
  it('lists the chat history, expanded', () => {
    renderSidebar();

    expect(kit.history.latest).toMatchObject({ isExpanded: true, isMobile: false });
  });

  it('tells the history it is on a phone', () => {
    renderSidebar({ isMobile: true });

    expect(kit.history.latest).toMatchObject({ isMobile: true });
  });

  it('does not pass a chat to highlight, the history follows the open chat itself', () => {
    renderSidebar();

    expect(kit.history.latest).not.toHaveProperty('currentChatId');
  });
});

describe('ChatSidebarContent on a phone', () => {
  it('lets the drawer know when a chat is chosen', () => {
    renderSidebar({ isMobile: true });

    fireEvent.click(screen.getByTestId('history-row'));

    expect(handlers.onMobileItemClick).toHaveBeenCalledTimes(1);
  });

  it('survives a chat being chosen when nothing is listening', () => {
    renderSidebar({ withItemClick: false });

    expect(() => fireEvent.click(screen.getByTestId('history-row'))).not.toThrow();
  });

  it.each([
    ['starting a new chat', () => fireEvent.click(screen.getByRole('button', { name: 'chat.newChat' })), 'onNewChat'],
    ['going home from the brand', () => fireEvent.click(screen.getByRole('button', { name: /MyrmAgent/ })), null],
    ['choosing a search result', () => fireEvent.click(screen.getByRole('button', { name: 'pick-result' })), null],
  ] as const)('lets the drawer know after %s', (_what, perform, handler) => {
    renderSidebar({ isMobile: true });

    perform();

    expect(handlers.onMobileItemClick).toHaveBeenCalledTimes(1);
    if (handler) {
      expect(handlers[handler]).toHaveBeenCalledTimes(1);
    }
  });

  it('leaves the drawer alone when the history is only browsed', () => {
    renderSidebar({ isMobile: true });

    fireEvent.click(screen.getByRole('button', { name: 'sidebar.searchPlaceholder' }));
    fireEvent.click(screen.getByRole('button', { name: 'chat.import.buttonTitle' }));

    expect(handlers.onMobileItemClick).not.toHaveBeenCalled();
  });
});

describe('ChatSidebarContent workspace files', () => {
  it.each([
    ['in a plain chat', { chatId: 'c-1', actionMode: 'fast' as const, workspaceDir: '/work/alpha' }],
    ['before the chat has an id', { chatId: undefined, actionMode: 'agent' as const, workspaceDir: '/work/alpha' }],
    ['without a workspace folder', { chatId: 'c-1', actionMode: 'agent' as const, workspaceDir: null }],
    ['with an empty workspace folder', { chatId: 'c-1', actionMode: 'agent' as const, workspaceDir: '' }],
  ])('has no Files tab %s', (_when, state) => {
    useChatStore.setState(state);
    renderSidebar();

    expect(screen.queryByRole('button', { name: 'sidebar.files' })).toBeNull();
    expect(screen.getByTestId('history-row')).toBeInTheDocument();
  });

  it('adds a Files tab to an agent chat that has a workspace folder', () => {
    openAgentChatWithWorkspace();
    renderSidebar();

    expect(chatTab()).toBeInTheDocument();
    expect(filesTab()).toBeInTheDocument();
    expect(screen.getByTestId('history-row')).toBeInTheDocument();
    expect(screen.queryByTestId('file-browser')).toBeNull();
  });

  it('shows the file browser for the workspace on the Files tab, and the history again on the chat tab', () => {
    openAgentChatWithWorkspace('/work/alpha');
    renderSidebar();

    fireEvent.click(filesTab());
    expect(screen.getByTestId('file-browser')).toHaveAttribute('data-path', '/work/alpha');
    expect(screen.queryByTestId('history-row')).toBeNull();

    fireEvent.click(chatTab());
    expect(screen.queryByTestId('file-browser')).toBeNull();
    expect(screen.getByTestId('history-row')).toBeInTheDocument();
  });

  it('reads the workspace files only while the Files tab is showing', () => {
    openAgentChatWithWorkspace('/work/alpha');
    renderSidebar();
    expect(kit.workspaceRequests.at(-1)).toBeNull();

    fireEvent.click(filesTab());
    expect(kit.workspaceRequests.at(-1)).toBe('/work/alpha');

    fireEvent.click(chatTab());
    expect(kit.workspaceRequests.at(-1)).toBeNull();
  });

  it('hands the file listing to the browser', () => {
    kit.workspace.current = { ...kit.workspace.current, loading: true, error: 'boom', truncated: true };
    openAgentChatWithWorkspace();
    renderSidebar();

    fireEvent.click(filesTab());
    const browser = screen.getByTestId('file-browser');

    expect(browser).toHaveAttribute('data-loading', 'true');
    expect(browser).toHaveAttribute('data-error', 'boom');
    expect(browser).toHaveAttribute('data-truncated', 'true');
    fireEvent.click(within(browser).getByRole('button', { name: 'refresh-files' }));
    fireEvent.click(within(browser).getByRole('button', { name: 'load-children' }));
    expect(kit.workspace.current.refresh).toHaveBeenCalledTimes(1);
    expect(kit.workspace.current.loadChildren).toHaveBeenCalledExactlyOnceWith('docs');
  });

  it('goes back to the chat history at once when the workspace folder goes away', () => {
    openAgentChatWithWorkspace();
    renderSidebar();
    fireEvent.click(filesTab());

    act(() => useChatStore.setState({ workspaceDir: null }));

    expect(screen.queryByRole('button', { name: 'sidebar.files' })).toBeNull();
    expect(screen.queryByTestId('file-browser')).toBeNull();
    expect(screen.getByTestId('history-row')).toBeInTheDocument();
  });

  it('goes back to the chat history when the chat is no longer an agent chat', () => {
    openAgentChatWithWorkspace();
    renderSidebar();
    fireEvent.click(filesTab());

    act(() => useChatStore.setState({ actionMode: 'fast' }));

    expect(screen.queryByTestId('file-browser')).toBeNull();
    expect(screen.getByTestId('history-row')).toBeInTheDocument();
  });

  it('opens the Files tab on the new folder when the workspace changes', () => {
    openAgentChatWithWorkspace('/work/alpha');
    renderSidebar();
    fireEvent.click(filesTab());

    act(() => useChatStore.setState({ chatId: 'c-2', workspaceDir: '/work/beta' }));

    expect(screen.getByTestId('file-browser')).toHaveAttribute('data-path', '/work/beta');
  });

  it('does not come back to the Files tab by itself once the workspace returns', () => {
    openAgentChatWithWorkspace();
    renderSidebar();
    fireEvent.click(filesTab());
    act(() => useChatStore.setState({ workspaceDir: null }));

    act(() => useChatStore.setState({ workspaceDir: '/work/alpha' }));

    expect(screen.getByTestId('history-row')).toBeInTheDocument();
  });
});

describe('ChatSidebarContent file preview', () => {
  function openPreviewOfNotes(): void {
    openAgentChatWithWorkspace('/work/alpha');
    renderSidebar();
    fireEvent.click(filesTab());
    fireEvent.click(screen.getByRole('button', { name: 'open-file' }));
  }

  it('previews a file that is clicked, in its workspace', () => {
    openPreviewOfNotes();

    expect(screen.getByTestId('file-preview')).toHaveAttribute('data-file', 'docs/notes.md');
    expect(screen.getByTestId('file-preview')).toHaveAttribute('data-workspace', '/work/alpha');
  });

  it('ignores a click on a folder', () => {
    openAgentChatWithWorkspace();
    renderSidebar();
    fireEvent.click(filesTab());

    fireEvent.click(screen.getByRole('button', { name: 'open-folder' }));

    expect(screen.queryByTestId('file-preview')).toBeNull();
  });

  it('closes the preview from its own close button', () => {
    openPreviewOfNotes();

    fireEvent.click(screen.getByRole('button', { name: 'close-preview' }));

    expect(screen.queryByTestId('file-preview')).toBeNull();
    expect(screen.getByTestId('file-browser')).toBeInTheDocument();
  });

  it('does not cover the chat history after switching to the chat tab', () => {
    openPreviewOfNotes();

    fireEvent.click(chatTab());

    expect(screen.queryByTestId('file-preview')).toBeNull();
    expect(screen.getByTestId('history-row')).toBeInTheDocument();
  });

  it('does not bring a preview back when the Files tab is opened again', () => {
    openPreviewOfNotes();

    fireEvent.click(chatTab());
    fireEvent.click(filesTab());

    expect(screen.queryByTestId('file-preview')).toBeNull();
    expect(screen.getByTestId('file-browser')).toBeInTheDocument();
  });

  it('does not show a file of another workspace after the workspace changes', () => {
    openPreviewOfNotes();

    act(() => useChatStore.setState({ chatId: 'c-2', workspaceDir: '/work/beta' }));

    expect(screen.queryByTestId('file-preview')).toBeNull();
    expect(screen.getByTestId('file-browser')).toHaveAttribute('data-path', '/work/beta');
  });
});

describe('ChatSidebarContent trash', () => {
  it('shows no count while the trash is empty', async () => {
    renderSidebar();
    await settle();

    expect(kit.trashCount).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /^title/ })).toBeInTheDocument();
    expect(screen.queryByText('0')).toBeNull();
  });

  it('shows how many chats are in the trash', async () => {
    kit.trashCount.mockResolvedValue(3);
    renderSidebar();
    await settle();

    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('shows no count, and no failure, when the count cannot be read', async () => {
    kit.trashCount.mockRejectedValue(new Error('offline'));
    renderSidebar();
    await settle();

    expect(screen.queryByText(/^\d+$/)).toBeNull();
    expect(screen.getByRole('button', { name: /^title/ })).toBeInTheDocument();
  });

  it('opens the trash panel in a side sheet', async () => {
    renderSidebar();
    await settle();

    fireEvent.click(screen.getByRole('button', { name: /^title/ }));

    expect(await screen.findByTestId('trash-panel')).toBeInTheDocument();
  });

  it('takes the count the panel reports', async () => {
    kit.trashCount.mockResolvedValue(3);
    renderSidebar();
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /^title/ }));

    fireEvent.click(await screen.findByRole('button', { name: 'set-count-5' }));

    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('lets a count the panel reports stand over an older read that finishes later', async () => {
    const older = deferred<number>();
    kit.trashCount.mockReturnValueOnce(older.promise);
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: /^title/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'set-count-5' }));

    await act(async () => older.resolve(9));

    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.queryByText('9')).toBeNull();
  });

  it('reads the count again when a chat is restored from the panel', async () => {
    kit.trashCount.mockResolvedValueOnce(3).mockResolvedValueOnce(2);
    renderSidebar();
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /^title/ }));

    fireEvent.click(await screen.findByRole('button', { name: 'restored' }));
    await settle();

    expect(kit.trashCount).toHaveBeenCalledTimes(2);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('reads the history list again when a chat is restored from the panel', async () => {
    const original = useChatStore.getState().loadChatHistory;
    const loadChatHistory = vi.fn<typeof original>().mockResolvedValue(undefined);
    useChatStore.setState({ loadChatHistory });
    try {
      renderSidebar();
      await settle();
      expect(loadChatHistory).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole('button', { name: /^title/ }));

      fireEvent.click(await screen.findByRole('button', { name: 'restored' }));
      await settle();

      expect(loadChatHistory).toHaveBeenCalledExactlyOnceWith(1, 20, { force: true });
    } finally {
      useChatStore.setState({ loadChatHistory: original });
    }
  });

  it('keeps the newest count when an older read finishes last', async () => {
    const older = deferred<number>();
    kit.trashCount.mockReturnValueOnce(older.promise).mockResolvedValueOnce(2);
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: /^title/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'restored' }));
    await settle();

    await act(async () => older.resolve(9));

    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.queryByText('9')).toBeNull();
  });
});
