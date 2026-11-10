import type { ReactNode } from 'react';
import { vi } from 'vitest';
import type { UseWorkspaceFilesReturn } from '@/components/features/workspace-browser/useWorkspaceFiles';
import type { FileEntry } from '@/services/chat';
import type { NavTab } from '../NavBar';

interface HistoryListProps {
  isExpanded: boolean;
  isMobile?: boolean;
  currentChatId?: string;
  onItemClick?: () => void;
}

interface ChatSidebarProps {
  onNewChat: () => void;
  onToggleCollapse: () => void;
  isMobile?: boolean;
  onMobileItemClick?: () => void;
}

interface NavBarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  onToggleSidebar: () => void;
  onCloseMobileSidebar?: () => void;
  isSidebarCollapsed: boolean;
  isSettingsPage: boolean;
  hideSidebarToggle?: boolean;
  isMobile?: boolean;
  lastChatUrl: string | null;
  lastWorkUrl: string | null;
  lastProjectsUrl: string | null;
  currentPathname: string;
}

interface BrowserProps {
  workspacePath: string;
  loading?: boolean;
  error?: string | null;
  truncated?: boolean;
  onRefresh?: () => void;
  onFileClick?: (file: FileEntry) => void;
  onLoadChildren: (dirPath: string) => Promise<void>;
}

interface PreviewProps {
  file: FileEntry;
  workspace: string;
  onClose: () => void;
}

export const noteFile: FileEntry = {
  name: 'notes.md',
  path: 'docs/notes.md',
  type: 'file',
  size: 12,
  mtime: null,
  is_text: true,
  children: null,
};
export const docsFolder: FileEntry = {
  name: 'docs',
  path: 'docs',
  type: 'directory',
  size: null,
  mtime: null,
  is_text: null,
  children: [noteFile],
};

const kit = vi.hoisted(() => {
  const emptyWorkspace = (): UseWorkspaceFilesReturn => ({
    files: [],
    loading: false,
    error: null,
    truncated: false,
    refresh: vi.fn(async () => undefined),
    loadChildren: vi.fn(async () => undefined),
  });
  return {
    push: vi.fn<(href: string) => void>(),
    pathname: { current: '/' },
    history: { latest: null as HistoryListProps | null },
    chatSidebar: { latest: null as ChatSidebarProps | null },
    navBar: { latest: null as NavBarProps | null },
    workspaceRequests: [] as (string | null)[],
    emptyWorkspace,
    workspace: { current: emptyWorkspace() },
    trashCount: vi.fn<() => Promise<number>>(),
  };
});
export { kit };

export function resetSidebarKit(): void {
  kit.push.mockReset();
  kit.pathname.current = '/';
  kit.history.latest = null;
  kit.chatSidebar.latest = null;
  kit.navBar.latest = null;
  kit.workspaceRequests.length = 0;
  kit.workspace.current = kit.emptyWorkspace();
  kit.trashCount.mockReset();
  kit.trashCount.mockResolvedValue(0);
}

/* ─── module mock factories (`vi.mock(path, async () => (await import('./sidebarKit')).xMock())`) ─── */

/** One router for every call, like Next's, so effects and callbacks keyed on it stay put between renders. */
const router = { push: kit.push };

export const navigationMock = () => ({
  useRouter: () => router,
  usePathname: () => kit.pathname.current,
});

export const brandLogoMock = () => ({ default: () => <span data-testid="brand-logo" /> });

export const importModalMock = () => ({
  default: ({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) => (
    <div data-testid="import-modal" data-open={String(open)}>
      <button type="button" onClick={() => onOpenChange(false)}>
        close-import
      </button>
    </div>
  ),
});

export const searchDialogMock = () => ({
  SearchDialog: ({
    open,
    onOpenChange,
    onPick,
    children,
  }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onPick?: () => void;
    children: ReactNode;
  }) => (
    <div data-testid="search-dialog" data-open={String(open)}>
      <button type="button" onClick={() => onOpenChange(false)}>
        close-search
      </button>
      <button type="button" onClick={() => onPick?.()}>
        pick-result
      </button>
      {children}
    </div>
  ),
  SearchTrigger: ({ placeholder, onOpenDialog }: { placeholder: string; onOpenDialog: () => void }) => (
    <button type="button" onClick={onOpenDialog}>
      {placeholder}
    </button>
  ),
});

export const historyListMock = () => ({
  default: (props: HistoryListProps) => {
    kit.history.latest = props;
    return (
      <button type="button" data-testid="history-row" onClick={() => props.onItemClick?.()}>
        row
      </button>
    );
  },
});

/** The sidebar body as the shell sees it: one button per callback it was given. */
export const chatSidebarMock = () => ({
  ChatSidebarContent: (props: ChatSidebarProps) => {
    kit.chatSidebar.latest = props;
    return (
      <div data-testid="chat-sidebar" data-mobile={String(Boolean(props.isMobile))}>
        <button type="button" onClick={props.onNewChat}>
          sidebar-new-chat
        </button>
        <button type="button" onClick={props.onToggleCollapse}>
          sidebar-collapse
        </button>
        <button type="button" onClick={() => props.onMobileItemClick?.()}>
          sidebar-item
        </button>
      </div>
    );
  },
});

/** The navigation rail: one button per tab plus the ways it asks the drawer to close. */
export const navBarMock = () => ({
  default: (props: NavBarProps) => {
    kit.navBar.latest = props;
    return (
      <nav data-testid="nav-bar">
        {(['chat', 'work', 'projects'] as const).map((tab) => (
          <button key={tab} type="button" onClick={() => props.onTabChange(tab)}>
            {`tab-${tab}`}
          </button>
        ))}
        <button type="button" onClick={props.onToggleSidebar}>
          rail-toggle
        </button>
        <button type="button" onClick={() => props.onCloseMobileSidebar?.()}>
          rail-close
        </button>
      </nav>
    );
  },
});

export const catchupMock = () => ({ CatchupInbox: () => <div data-testid="catchup-inbox" /> });

export const extensionSlotMock = () => ({
  ExtensionSlot: ({ name }: { name: string }) => <div data-testid={`slot:${name}`} />,
});

export const trashPanelMock = () => ({
  default: ({ onRestored, onCountChange }: { onRestored?: () => void; onCountChange?: (count: number) => void }) => (
    <div data-testid="trash-panel">
      <button type="button" onClick={() => onCountChange?.(5)}>
        set-count-5
      </button>
      <button type="button" onClick={() => onRestored?.()}>
        restored
      </button>
    </div>
  ),
});

export const chatTrashMock = async (importOriginal: () => Promise<typeof import('@/services/chatTrash')>) => ({
  ...(await importOriginal()),
  getTrashCount: () => kit.trashCount(),
});

export const workspaceFilesMock = () => ({
  useWorkspaceFiles: (workspaceDir: string | null): UseWorkspaceFilesReturn => {
    kit.workspaceRequests.push(workspaceDir);
    return kit.workspace.current;
  },
});

const FileBrowserStub = (props: BrowserProps) => (
  <div
    data-testid="file-browser"
    data-path={props.workspacePath}
    data-loading={String(Boolean(props.loading))}
    data-error={props.error ?? ''}
    data-truncated={String(Boolean(props.truncated))}
  >
    <button type="button" onClick={() => props.onFileClick?.(noteFile)}>
      open-file
    </button>
    <button type="button" onClick={() => props.onFileClick?.(docsFolder)}>
      open-folder
    </button>
    <button type="button" onClick={() => props.onRefresh?.()}>
      refresh-files
    </button>
    <button type="button" onClick={() => void props.onLoadChildren('docs')}>
      load-children
    </button>
  </div>
);

const FilePreviewStub = (props: PreviewProps) => (
  <div data-testid="file-preview" data-file={props.file.path} data-workspace={props.workspace}>
    <button type="button" onClick={props.onClose}>
      close-preview
    </button>
  </div>
);

/** `next/dynamic` that resolves the two workspace panels synchronously, picking the stub by the loader's import. */
export const nextDynamicMock = () => ({
  default: (loader: () => Promise<unknown>) => {
    const source = String(loader);
    if (source.includes('WorkspaceFileBrowser')) {
      return FileBrowserStub;
    }
    if (source.includes('WorkspaceFilePreview')) {
      return FilePreviewStub;
    }
    return () => null;
  },
});
