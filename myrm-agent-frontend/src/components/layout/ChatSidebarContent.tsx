'use client';

/**
 * 聊天侧边栏内容组件
 *
 * [INPUT]
 * - onNewChat: 新建对话回调
 * - onToggleCollapse: 侧边栏折叠切换回调
 * - isMobile: 是否移动端模式
 * - onMobileItemClick: 移动端项目点击回调
 *
 * [OUTPUT]
 * - ChatSidebarContent: 聊天侧边栏内容组件
 *   - 聊天历史列表
 *   - CLI 工作区文件树（Tauri 环境，ACP 模式）
 *   - Web 工作区文件浏览器（Web/SaaS，主 Agent 模式）
 *
 * [POS]
 * 侧边栏聊天内容区域。显示搜索、新建对话按钮、聊天历史列表。
 * 在 Tauri+ACP 模式下使用 CLIWorkspaceTree，在 Web/SaaS+主Agent
 * 模式下使用 WorkspaceFileBrowser 显示 Chat/Files Tab 切换。
 */

import { memo, useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import BrandLogo from '@/components/ui/BrandLogo';
import { FolderOpen, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { SearchDialog, SearchTrigger } from '@/components/ui/search-dialog';
import ChatHistoryList from '@/components/ui/sidebar/ChatHistoryList';
import {
  CLIWorkspaceTree,
  CLIFilePreview,
  CLIContextMenu,
  useFileWatcher,
  useFilePreview,
} from '@/components/ui/cli-visualization';
import type { FileNode } from '@/components/ui/cli-visualization/CLIWorkspaceTree';
import { WorkspaceFileBrowser, WorkspaceFilePreview, useWorkspaceFiles } from '@/components/ui/workspace-browser';
import { useWorkingDirectory } from '@/store/useCLIAgentStore';
import useChatStore from '@/store/useChatStore';
import { type FileEntry } from '@/services/chat';
import { isTauriEnvironment } from '@/lib/tauri';
import { CatchupInbox } from '@/components/ui/chat-window/catchup/CatchupInbox';
import SessionTrashPanel from '@/components/ui/chat-window/SessionTrashPanel';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { getTrashCount } from '@/services/chatTrash';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

export interface ChatSidebarContentProps {
  onNewChat: () => void;
  onToggleCollapse: () => void;
  isMobile?: boolean;
  onMobileItemClick?: () => void;
}

const SidebarCollapseIcon = memo(() => (
  <svg width="20" height="20" fill="none" viewBox="0 0 20 20" className="text-muted-foreground">
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M2.167 6.667A2.833 2.833 0 0 1 5 3.833h2.708v12.334H5a2.833 2.833 0 0 1-2.833-2.834V6.667ZM9.042 17.5H5a4.167 4.167 0 0 1-4.167-4.167V6.667A4.167 4.167 0 0 1 5 2.5h10a4.167 4.167 0 0 1 4.167 4.167v6.666A4.167 4.167 0 0 1 15 17.5H9.042Zm0-13.667H15a2.833 2.833 0 0 1 2.833 2.834v6.666A2.833 2.833 0 0 1 15 16.167H9.042V3.833ZM3.583 6.5c0-.368.336-.667.75-.667H5.75c.414 0 .75.299.75.667 0 .368-.336.667-.75.667H4.333c-.414 0-.75-.299-.75-.667Zm.75 1.833c-.414 0-.75.299-.75.667 0 .368.336.667.75.667H5.75c.414 0 .75-.299.75-.667 0-.368-.336-.667-.75-.667H4.333Z"
      fill="currentColor"
    />
  </svg>
));
SidebarCollapseIcon.displayName = 'SidebarCollapseIcon';

const TrashButton = memo(function TrashButton() {
  const t = useTranslations('chat.trash');
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);

  const refreshCount = useCallback(async () => {
    try {
      const c = await getTrashCount();
      setCount(c);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    refreshCount();
  }, [refreshCount]);

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
        <SheetContent side="left" className="w-[400px] sm:w-[540px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{t('title')}</SheetTitle>
          </SheetHeader>
          <div className="mt-4">
            <SessionTrashPanel onRestored={refreshCount} onCountChange={setCount} />
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

    // -----------------------------------------------------------------------
    // ACP/CLI workspace (Tauri only)
    // -----------------------------------------------------------------------
    const cliWorkingDirectory = useWorkingDirectory();
    const showCliWorkspace = isTauriEnvironment() && !!cliWorkingDirectory;

    // -----------------------------------------------------------------------
    // Main Agent workspace (Web/SaaS)
    // -----------------------------------------------------------------------
    const chatId = useChatStore((s) => s.chatId);
    const actionMode = useChatStore((s) => s.actionMode);
    const workspaceDir = useChatStore((s) => s.workspaceDir);
    const [webWorkspaceDir, setWebWorkspaceDir] = useState<string | null>(null);

    useEffect(() => {
      if (!chatId || actionMode !== 'agent') {
        setWebWorkspaceDir(null);
        return;
      }
      setWebWorkspaceDir(workspaceDir);
    }, [chatId, actionMode, workspaceDir]);

    const showWebWorkspace = !isTauriEnvironment() && actionMode === 'agent' && !!webWorkspaceDir;
    const showTabs = showCliWorkspace || showWebWorkspace;

    const [activeView, setActiveView] = useState<'chat' | 'workspace'>('chat');

    useEffect(() => {
      if (!showTabs && activeView === 'workspace') setActiveView('chat');
    }, [showTabs, activeView]);

    // ACP file watcher (Tauri FS)
    const {
      files: cliFiles,
      loading: cliFilesLoading,
      refresh: cliRefresh,
    } = useFileWatcher(showCliWorkspace && activeView === 'workspace' ? cliWorkingDirectory : undefined);

    // Web file browser (HTTP API)
    const {
      files: webFiles,
      loading: webFilesLoading,
      error: webFilesError,
      truncated: webFilesTruncated,
      refresh: webRefresh,
    } = useWorkspaceFiles(showWebWorkspace && activeView === 'workspace' ? webWorkspaceDir : null);

    // ACP file preview (Tauri)
    const {
      previewFile,
      isOpen: isPreviewOpen,
      content,
      fileType,
      language,
      loading: previewLoading,
      error: previewError,
      openPreview,
      closePreview,
    } = useFilePreview();

    // Web file preview state
    const [webPreviewFile, setWebPreviewFile] = useState<FileEntry | null>(null);

    // ACP context menu
    const [contextMenu, setContextMenu] = useState<{
      visible: boolean;
      position: { x: number; y: number };
      file: FileNode | null;
    }>({ visible: false, position: { x: 0, y: 0 }, file: null });

    const handleCliFileClick = useCallback(
      (file: FileNode) => {
        if (file.type === 'file') openPreview(file);
      },
      [openPreview],
    );

    const handleCliFileRightClick = useCallback((file: FileNode, event: React.MouseEvent) => {
      setContextMenu({ visible: true, position: { x: event.clientX, y: event.clientY }, file });
    }, []);

    const closeContextMenu = useCallback(() => {
      setContextMenu((prev) => ({ ...prev, visible: false }));
    }, []);

    const handleOpenInEditor = useCallback(async () => {
      if (!contextMenu.file || !isTauriEnvironment()) return;
      try {
        const shell = await import('@tauri-apps/plugin-shell');
        await shell.open(contextMenu.file.path);
      } catch (error) {
        console.error('Failed to open in editor:', error);
      }
    }, [contextMenu.file]);

    const handleShowInFinder = useCallback(async () => {
      if (!contextMenu.file || !isTauriEnvironment()) return;
      try {
        const shell = await import('@tauri-apps/plugin-shell');
        const dirPath =
          contextMenu.file.type === 'directory'
            ? contextMenu.file.path
            : contextMenu.file.path.substring(0, contextMenu.file.path.lastIndexOf('/'));
        await shell.open(dirPath);
      } catch (error) {
        console.error('Failed to show in Finder:', error);
      }
    }, [contextMenu.file]);

    const handleCopyPath = useCallback(async () => {
      if (!contextMenu.file) return;
      try {
        await writeToClipboard(contextMenu.file.path);
      } catch (error) {
        console.error('Failed to copy path:', error);
      }
    }, [contextMenu.file]);

    const handleWebFileClick = useCallback((file: FileEntry) => {
      if (file.type === 'file') setWebPreviewFile(file);
    }, []);

    return (
      <div className="flex flex-col h-full">
        {/* Header: Logo + Collapse Button */}
        <div className="p-3 flex items-center justify-between flex-shrink-0">
          <button
            onClick={() => router.push('/')}
            className="flex items-center gap-2 hover:opacity-80 transition-opacity"
            aria-label="Home"
          >
            <BrandLogo size={40} priority className="w-10 h-10" />
            <span className="text-lg font-semibold brand-gradient-text">MyrmAgent</span>
          </button>
          <div className="flex items-center gap-1">
            <CatchupInbox />
            <button
              onClick={onToggleCollapse}
              className="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-muted transition-colors text-muted-foreground"
              aria-label={t('common.collapseMenu')}
            >
              <SidebarCollapseIcon />
            </button>
          </div>
        </div>

        <div className="mx-3 border-t border-border/50" />

        {/* Search */}
        <div className="p-3 flex-shrink-0">
          <SearchDialog open={searchDialogOpen} onOpenChange={setSearchDialogOpen}>
            <SearchTrigger
              placeholder={t('sidebar.searchPlaceholder')}
              onOpenDialog={() => setSearchDialogOpen(true)}
            />
          </SearchDialog>
        </div>

        {/* New Chat Button */}
        <div className="px-3 pb-3 flex-shrink-0">
          <button
            onClick={onNewChat}
            className={cn(
              'w-full flex items-center gap-3 p-2.5 rounded-xl cursor-pointer text-sm brand-interactive-hover',
              'bg-background dark:bg-background',
              'border border-border/60 dark:border-border/60',
              'text-foreground dark:text-foreground',
              'transition-all duration-200 ease-in-out',
              'active:scale-[0.98]',
            )}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="text-current"
            >
              <path
                d="M12.5 14.5v-6m-3 3h6m-3 8.5a8.5 8.5 0 1 0-8.057-5.783c.108.32.162.481.172.604a.899.899 0 0 1-.028.326c-.03.12-.098.245-.232.494l-1.636 3.027c-.233.432-.35.648-.324.815a.5.5 0 0 0 .234.35c.144.087.388.062.876.011l5.121-.529c.155-.016.233-.024.303-.021.07.002.12.009.187.024.069.016.155.05.329.116A8.478 8.478 0 0 0 12.5 20z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="whitespace-nowrap">{t('chat.newChat')}</span>
          </button>
        </div>

        {/* Tab: Chat / Files (when workspace available) */}
        {showTabs && (
          <div className="px-3 pb-2 flex gap-1 flex-shrink-0">
            <button
              onClick={() => setActiveView('chat')}
              className={cn(
                'flex-1 py-1.5 px-3 text-sm rounded-lg transition-colors',
                activeView === 'chat' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50',
              )}
            >
              {t('sidebar.chatHistory')}
            </button>
            <button
              onClick={() => setActiveView('workspace')}
              className={cn(
                'flex-1 py-1.5 px-3 text-sm rounded-lg transition-colors',
                activeView === 'workspace' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50',
              )}
            >
              {showCliWorkspace ? t('sidebar.workspace') : t('sidebar.files')}
            </button>
          </div>
        )}

        {/* Content area */}
        <div className="flex-1 overflow-y-auto relative">
          {activeView === 'chat' ? (
            <>
              <ChatHistoryList
                isExpanded={true}
                currentChatId={undefined}
                isMobile={isMobile}
                onItemClick={onMobileItemClick}
              />
              <TrashButton />
            </>
          ) : showCliWorkspace ? (
            <CLIWorkspaceTree
              workspacePath={cliWorkingDirectory!}
              files={cliFiles}
              loading={cliFilesLoading}
              onRefresh={cliRefresh}
              onFileClick={handleCliFileClick}
              onFileRightClick={handleCliFileRightClick}
            />
          ) : showWebWorkspace && webWorkspaceDir ? (
            <WorkspaceFileBrowser
              workspacePath={webWorkspaceDir}
              files={webFiles}
              loading={webFilesLoading}
              error={webFilesError}
              truncated={webFilesTruncated}
              onRefresh={webRefresh}
              onFileClick={handleWebFileClick}
            />
          ) : actionMode === 'agent' && !webWorkspaceDir ? (
            <div className="flex flex-col items-center justify-center py-8 px-4 text-muted-foreground">
              <FolderOpen className="h-8 w-8 mb-2" />
              <p className="text-sm text-center mb-3">{t('workspace.selectDir')}</p>
            </div>
          ) : null}
        </div>

        {/* ACP file preview (Tauri) */}
        {isPreviewOpen && previewFile && (
          <div className="absolute inset-0 z-50 bg-background">
            <CLIFilePreview
              file={previewFile}
              content={content}
              fileType={fileType}
              language={language}
              loading={previewLoading}
              error={previewError}
              onClose={closePreview}
              onOpenInEditor={handleOpenInEditor}
              onShowInFinder={handleShowInFinder}
            />
          </div>
        )}

        {/* Web file preview */}
        {webPreviewFile && webWorkspaceDir && (
          <div className="absolute inset-0 z-50 bg-background">
            <WorkspaceFilePreview
              file={webPreviewFile}
              workspace={webWorkspaceDir}
              onClose={() => setWebPreviewFile(null)}
            />
          </div>
        )}

        {/* ACP context menu */}
        {contextMenu.visible && contextMenu.file && (
          <CLIContextMenu
            position={contextMenu.position}
            file={contextMenu.file}
            visible={contextMenu.visible}
            onPreview={() => {
              if (contextMenu.file) openPreview(contextMenu.file);
            }}
            onOpenInEditor={handleOpenInEditor}
            onShowInFinder={handleShowInFinder}
            onCopyPath={handleCopyPath}
            onClose={closeContextMenu}
          />
        )}
      </div>
    );
  },
);

ChatSidebarContent.displayName = 'ChatSidebarContent';

export default ChatSidebarContent;
