'use client';

/**
 * 聊天侧边栏内容组件
 *
 * [INPUT]
 * - onNewChat: 新建对话回调
 * - onToggleCollapse: 侧边栏折叠切换回调
 * - isMobile: 是否移动端模式
 * - onMobileItemClick: 用户选定会话 / 新建对话 / 回到首页 / 选定搜索结果后的回调（移动端用来关闭抽屉）
 *
 * [OUTPUT]
 * - ChatSidebarContent: 聊天侧边栏内容组件
 *   - 聊天历史列表与回收站入口
 *   - Agent vault 文件浏览器（主 Agent 对话已有工作目录时）
 *
 * [POS]
 * 侧边栏聊天内容区域。显示搜索、新建对话按钮、聊天历史列表。
 * 主 Agent 对话有 workspaceDir 时多出「文件」页签，显示 WorkspaceFileBrowser（含 P1 SSE 自动刷新）。
 */

import { memo, useState, useCallback, useEffect, useRef, Suspense } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import BrandLogo from '@/components/features/app-shell/BrandLogo';
import { Trash2, UploadCloud } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import SessionImportModal from '@/components/features/sidebar/SessionImportModal';
import { SearchDialog, SearchTrigger } from '@/components/features/app-shell/search-dialog';
import ChatHistoryList from '@/components/features/sidebar/ChatHistoryList';
import { useWorkspaceFiles } from '@/components/features/workspace-browser/useWorkspaceFiles';
import useChatStore from '@/store/useChatStore';
import { type FileEntry } from '@/services/chat';
import { ExtensionSlot } from '@/components/features/extension-slots';
import { CatchupInbox } from '@/components/features/chat-window/catchup/CatchupInbox';
import SessionTrashPanel from '@/components/features/chat-window/SessionTrashPanel';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import { getTrashCount } from '@/services/chatTrash';
import { SidebarPanelIcon } from './SidebarPanelIcon';

const sidebarPanelLoading = (
  <div className="flex h-full items-center justify-center p-6">
    <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
  </div>
);

const WorkspaceFileBrowser = dynamic(
  () =>
    import('@/components/features/workspace-browser/WorkspaceFileBrowser').then((module) => ({
      default: module.WorkspaceFileBrowser,
    })),
  { ssr: false, loading: () => sidebarPanelLoading },
);

const WorkspaceFilePreview = dynamic(
  () =>
    import('@/components/features/workspace-browser/WorkspaceFilePreview').then((module) => ({
      default: module.WorkspaceFilePreview,
    })),
  { ssr: false },
);

interface ChatSidebarContentProps {
  onNewChat: () => void;
  onToggleCollapse: () => void;
  isMobile?: boolean;
  onMobileItemClick?: () => void;
}

type SidebarView = 'chat' | 'workspace';

const TrashButton = memo(function TrashButton() {
  const t = useTranslations('chat.trash');
  const loadChatHistory = useChatStore((state) => state.loadChatHistory);
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  // Counts come from our own reads and from the panel; only the newest one may stand.
  const latestCount = useRef(0);

  const showCount = useCallback((next: number) => {
    latestCount.current += 1;
    setCount(next);
  }, []);

  const refreshCount = useCallback(async () => {
    const read = ++latestCount.current;
    try {
      const next = await getTrashCount();
      if (read === latestCount.current) {
        setCount(next);
      }
    } catch {
      // The badge is a convenience: a failed read keeps what it already shows.
    }
  }, []);

  useEffect(() => {
    refreshCount();
  }, [refreshCount]);

  // A restored chat belongs back in the history list, which is otherwise only read when it is empty.
  const handleRestored = useCallback(() => {
    void refreshCount();
    void loadChatHistory(1, 20, { force: true });
  }, [refreshCount, loadChatHistory]);

  return (
    <div className="px-3 py-2 border-t border-border/30">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <button
            className={cn(
              'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm',
              'text-muted-foreground hover:text-foreground hover:bg-muted/50',
              'transition-colors duration-150',
            )}
          >
            <Trash2 size={16} />
            <span>{t('title')}</span>
            {count > 0 && <span className="ml-auto text-xs bg-muted px-1.5 py-0.5 rounded-full">{count}</span>}
          </button>
        </SheetTrigger>
        <SheetContent side="left" className="w-full max-w-[400px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{t('title')}</SheetTitle>
          </SheetHeader>
          <div className="mt-4">
            <SessionTrashPanel onRestored={handleRestored} onCountChange={showCount} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
});

export const ChatSidebarContent = memo<ChatSidebarContentProps>(
  ({ onNewChat, onToggleCollapse, isMobile = false, onMobileItemClick }) => {
    const t = useTranslations();
    const router = useRouter();
    const [searchDialogOpen, setSearchDialogOpen] = useState(false);
    const [importModalOpen, setImportModalOpen] = useState(false);

    // -----------------------------------------------------------------------
    // Main Agent workspace (Web/SaaS): only a saved agent chat that has a folder has files to show.
    // -----------------------------------------------------------------------
    const chatId = useChatStore((s) => s.chatId);
    const actionMode = useChatStore((s) => s.actionMode);
    const workspaceDir = useChatStore((s) => s.workspaceDir);
    const webWorkspaceDir = chatId && actionMode === 'agent' && workspaceDir ? workspaceDir : null;

    const [activeView, setActiveView] = useState<SidebarView>('chat');
    // The Files page goes away together with the workspace and does not come back when a workspace does.
    if (webWorkspaceDir === null && activeView === 'workspace') {
      setActiveView('chat');
    }
    const filesDir = activeView === 'workspace' ? webWorkspaceDir : null;

    // Web file browser (HTTP API)
    const {
      files: webFiles,
      loading: webFilesLoading,
      error: webFilesError,
      truncated: webFilesTruncated,
      refresh: webRefresh,
      loadChildren: webLoadChildren,
    } = useWorkspaceFiles(filesDir);

    // A preview belongs to the Files page and to the folder it was opened from: off that page `filesDir` is null.
    const [preview, setPreview] = useState<{ workspace: string; file: FileEntry } | null>(null);
    const openPreview = preview?.workspace === filesDir ? preview : null;

    const showView = (view: SidebarView) => {
      setActiveView(view);
      setPreview(null);
    };

    const handleWebFileClick = useCallback(
      (file: FileEntry) => {
        if (file.type === 'file' && webWorkspaceDir !== null) {
          setPreview({ workspace: webWorkspaceDir, file });
        }
      },
      [webWorkspaceDir],
    );

    const handleHome = () => {
      router.push('/');
      onMobileItemClick?.();
    };

    const handleNewChat = () => {
      onNewChat();
      onMobileItemClick?.();
    };

    return (
      <div className="flex flex-col h-full">
        {/* Header: Logo + Collapse Button */}
        <div className="p-3 flex items-center justify-between flex-shrink-0">
          <button onClick={handleHome} className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <BrandLogo size={56} priority decorative className="w-10 h-10" />
            <span className="text-lg font-semibold brand-gradient-text">MyrmAgent</span>
          </button>
          <div className="flex items-center gap-1">
            <CatchupInbox />
            <button
              onClick={onToggleCollapse}
              className="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-muted transition-colors text-muted-foreground"
              aria-label={t('common.collapseMenu')}
            >
              <SidebarPanelIcon />
            </button>
          </div>
        </div>

        <div className="mx-3 border-t border-border/50" />

        {/* Search */}
        <div className="p-3 flex-shrink-0">
          <SearchDialog open={searchDialogOpen} onOpenChange={setSearchDialogOpen} onPick={onMobileItemClick}>
            <SearchTrigger
              placeholder={t('sidebar.searchPlaceholder')}
              onOpenDialog={() => setSearchDialogOpen(true)}
            />
          </SearchDialog>
        </div>

        {/* New Chat & Import Session Buttons */}
        <div className="px-3 pb-3 flex-shrink-0 flex items-center gap-2">
          <button
            onClick={handleNewChat}
            className={cn(
              'flex-1 flex items-center gap-2.5 p-2.5 rounded-xl cursor-pointer text-sm brand-interactive-hover',
              'bg-background dark:bg-background',
              'border border-border/60 dark:border-border/60',
              'text-foreground dark:text-foreground',
              'transition-all duration-200 ease-in-out',
              'active:scale-[0.98]',
            )}
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="text-current flex-shrink-0"
            >
              <path
                d="M12.5 14.5v-6m-3 3h6m-3 8.5a8.5 8.5 0 1 0-8.057-5.783c.108.32.162.481.172.604a.899.899 0 0 1-.028.326c-.03.12-.098.245-.232.494l-1.636 3.027c-.233.432-.35.648-.324.815a.5.5 0 0 0 .234.35c.144.087.388.062.876.011l5.121-.529c.155-.016.233-.024.303-.021.07.002.12.009.187.024.069.016.155.05.329.116A8.478 8.478 0 0 0 12.5 20z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="whitespace-nowrap font-medium">{t('chat.newChat')}</span>
          </button>
          <button
            onClick={() => setImportModalOpen(true)}
            data-testid="import-session-btn"
            className={cn(
              'p-2.5 rounded-xl cursor-pointer text-sm brand-interactive-hover flex items-center justify-center flex-shrink-0',
              'bg-background dark:bg-background',
              'border border-border/60 dark:border-border/60',
              'text-muted-foreground hover:text-foreground',
              'transition-all duration-200 ease-in-out',
              'active:scale-[0.98]',
            )}
            title={t('chat.import.buttonTitle')}
            aria-label={t('chat.import.buttonTitle')}
          >
            <UploadCloud size={18} />
          </button>
        </div>

        {/* Tab: Chat / Files (when workspace available) */}
        {webWorkspaceDir !== null && (
          <div className="px-3 pb-2 flex gap-1 flex-shrink-0">
            <button
              onClick={() => showView('chat')}
              className={cn(
                'flex-1 py-1.5 px-3 text-sm rounded-lg transition-colors',
                activeView === 'chat' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50',
              )}
            >
              {t('sidebar.chatHistory')}
            </button>
            <button
              onClick={() => showView('workspace')}
              className={cn(
                'flex-1 py-1.5 px-3 text-sm rounded-lg transition-colors',
                activeView === 'workspace' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50',
              )}
            >
              {t('sidebar.files')}
            </button>
          </div>
        )}

        {/* Content area */}
        <div className="flex-1 overflow-y-auto relative">
          {filesDir !== null ? (
            <Suspense fallback={sidebarPanelLoading}>
              <WorkspaceFileBrowser
                workspacePath={filesDir}
                files={webFiles}
                loading={webFilesLoading}
                error={webFilesError}
                truncated={webFilesTruncated}
                onRefresh={webRefresh}
                onFileClick={handleWebFileClick}
                onLoadChildren={webLoadChildren}
              />
            </Suspense>
          ) : (
            <>
              <ChatHistoryList isExpanded isMobile={isMobile} onItemClick={onMobileItemClick} />
              <TrashButton />
            </>
          )}

          {openPreview ? (
            <Suspense fallback={sidebarPanelLoading}>
              <div className="absolute inset-0 z-10 bg-background">
                <WorkspaceFilePreview
                  file={openPreview.file}
                  workspace={openPreview.workspace}
                  onClose={() => setPreview(null)}
                  className="h-full"
                />
              </div>
            </Suspense>
          ) : null}
        </div>

        {/* Extension Slot: 侧边栏底部操作区 */}
        <ExtensionSlot name="sidebar.footer.action" className="px-3 pb-2 pt-1 border-t border-border/40" />

        {/* Modal: 跨工具会话纯净导入 */}
        <SessionImportModal open={importModalOpen} onOpenChange={setImportModalOpen} />
      </div>
    );
  },
);

ChatSidebarContent.displayName = 'ChatSidebarContent';
