import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useChatStore from '@/store/useChatStore';
import { MobileSidebarDrawer } from '../MobileSidebarDrawer';
import { kit, resetSidebarKit } from './sidebarKit';

vi.mock('next/navigation', async () => (await import('./sidebarKit')).navigationMock());
vi.mock('next/dynamic', async () => (await import('./sidebarKit')).nextDynamicMock());
vi.mock('../NavBar', async () => (await import('./sidebarKit')).navBarMock());
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
  onClose: vi.fn<() => void>(),
  onTabChange: vi.fn<(tab: string) => void>(),
  initializeChat: vi.fn<(id?: string) => void>(),
};

type DrawerProps = React.ComponentProps<typeof MobileSidebarDrawer>;

function renderDrawer(props: Partial<DrawerProps> = {}) {
  return render(
    <MobileSidebarDrawer
      isOpen
      onClose={handlers.onClose}
      activeTab="chat"
      onTabChange={handlers.onTabChange}
      isSettingsPage={false}
      shouldShowContentSidebar
      lastChatUrl="/c-1"
      lastWorkUrl="/work"
      lastProjectsUrl="/projects"
      currentPathname="/c-1"
      {...props}
    />,
  );
}

const backdrop = (container: HTMLElement) => container.querySelector<HTMLElement>('[role="presentation"]');
const panel = (container: HTMLElement) => container.querySelector<HTMLElement>('.fixed.top-0.left-0');

beforeEach(() => {
  resetSidebarKit();
  useChatStore.setState({
    chatId: undefined,
    actionMode: 'fast',
    workspaceDir: null,
    initializeChat: handlers.initializeChat,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('MobileSidebarDrawer opening and closing', () => {
  it('slides in over a dimmed page when open', () => {
    const { container } = renderDrawer();

    expect(panel(container)).toHaveClass('translate-x-0');
    expect(backdrop(container)).not.toBeNull();
  });

  it('keeps the page clear and the drawer out of view when closed', () => {
    const { container } = renderDrawer({ isOpen: false });

    expect(panel(container)).toHaveClass('-translate-x-full');
    expect(backdrop(container)).toBeNull();
  });

  it('closes when the dimmed page is tapped', () => {
    const { container } = renderDrawer();

    fireEvent.click(backdrop(container) as HTMLElement);

    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it('builds the sidebar body only while open and only on tabs that have one', () => {
    const { rerender } = renderDrawer({ isOpen: false });
    expect(screen.queryByTestId('history-row')).toBeNull();

    rerender(
      <MobileSidebarDrawer
        isOpen
        onClose={handlers.onClose}
        activeTab="chat"
        onTabChange={handlers.onTabChange}
        isSettingsPage={false}
        shouldShowContentSidebar
        lastChatUrl={null}
        lastWorkUrl={null}
        lastProjectsUrl={null}
        currentPathname="/"
      />,
    );
    expect(screen.getByTestId('history-row')).toBeInTheDocument();

    rerender(
      <MobileSidebarDrawer
        isOpen
        onClose={handlers.onClose}
        activeTab="work"
        onTabChange={handlers.onTabChange}
        isSettingsPage={false}
        shouldShowContentSidebar={false}
        lastChatUrl={null}
        lastWorkUrl={null}
        lastProjectsUrl={null}
        currentPathname="/work"
      />,
    );
    expect(screen.queryByTestId('history-row')).toBeNull();
  });
});

describe('MobileSidebarDrawer navigation rail', () => {
  it('shows the rail for the current tab, expanded, with the places the user was last', () => {
    renderDrawer({ activeTab: 'work', isSettingsPage: true, currentPathname: '/settings/models' });

    expect(kit.navBar.latest).toMatchObject({
      activeTab: 'work',
      isSidebarCollapsed: false,
      isSettingsPage: true,
      hideSidebarToggle: true,
      isMobile: true,
      lastChatUrl: '/c-1',
      lastWorkUrl: '/work',
      lastProjectsUrl: '/projects',
      currentPathname: '/settings/models',
    });
  });

  it('stays open when the chat tab is chosen, so a chat can be picked from the list', () => {
    renderDrawer({ activeTab: 'work', shouldShowContentSidebar: false });

    fireEvent.click(screen.getByRole('button', { name: 'tab-chat' }));

    expect(handlers.onTabChange).toHaveBeenCalledExactlyOnceWith('chat');
    expect(handlers.onClose).not.toHaveBeenCalled();
  });

  it.each(['work', 'projects'] as const)('closes when the %s tab is chosen, the page is the destination', (tab) => {
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: `tab-${tab}` }));

    expect(handlers.onTabChange).toHaveBeenCalledExactlyOnceWith(tab);
    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it('closes from the rail toggle and from the rail asking to close', () => {
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: 'rail-toggle' }));
    fireEvent.click(screen.getByRole('button', { name: 'rail-close' }));

    expect(handlers.onClose).toHaveBeenCalledTimes(2);
  });
});

describe('MobileSidebarDrawer sidebar body', () => {
  it('closes from the collapse button', () => {
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: 'common.collapseMenu' }));

    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it('closes once a chat is tapped, so the chat is not left behind the drawer', () => {
    renderDrawer();

    fireEvent.click(screen.getByTestId('history-row'));

    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it('closes once a new chat is started', () => {
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: 'chat.newChat' }));

    expect(handlers.initializeChat).toHaveBeenCalledTimes(1);
    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it('closes once the brand takes the user home', () => {
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: /MyrmAgent/ }));

    expect(kit.push).toHaveBeenCalledExactlyOnceWith('/');
    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it('closes once a search result is chosen', () => {
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: 'pick-result' }));

    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it('stays open while the user only searches or opens the import dialog', () => {
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: 'sidebar.searchPlaceholder' }));
    fireEvent.click(screen.getByRole('button', { name: 'chat.import.buttonTitle' }));

    expect(handlers.onClose).not.toHaveBeenCalled();
  });
});
