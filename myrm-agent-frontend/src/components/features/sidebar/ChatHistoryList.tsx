'use client';

import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { formatRelativeTime } from '@/lib/utils/relativeTime';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, memo, useMemo, useRef, type DragEvent } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useShallow } from 'zustand/react/shallow';
import { ChatHistoryDialogs } from './ChatHistoryDialogs';
import { DateGroupSection, PinnedSection, type HistoryRowProps } from './ChatHistorySections';
import { ChatHistoryToolbar } from './ChatHistoryToolbar';
import { groupChatsByDate, useCollapsedGroups } from './dateGroupUtils';
import BatchOperationBar from './BatchOperationBar';
import ProjectBar from './ProjectBar';
import ProjectMilestonePanel from './ProjectMilestonePanel';
import { useBatchMode } from './useBatchMode';
import { useChatActions } from './useChatActions';
import { useHistorySearch } from './useHistorySearch';
import { useProjectStore } from '@/store/useProjectStore';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { createPriorChatDragStartHandler } from '@/lib/chat/priorChatDrag';

interface ChatHistoryListProps {
  isExpanded: boolean;
  isMobile?: boolean;
  onItemClick?: () => void;
}

const ChatHistoryList = memo<ChatHistoryListProps>(({ isExpanded, isMobile = false, onItemClick }) => {
  const t = useTranslations();

  // Only what the list shows: the rest of the chat store (draft text, streaming messages) changes many times a
  // second, and a whole-store subscription would redraw every row each time.
  const {
    chatHistoryItems,
    chatHistoryPagination,
    chatHistoryLoading,
    chatHistoryError,
    chatHistorySourceFilter,
    chatHistorySearchKeyword,
    chatHistoryAvailableSources,
    loadChatHistory,
    loadMoreChatHistory,
    setChatHistorySourceFilter,
    setChatHistorySearchKeyword,
    activeChatId,
    isActiveLoading,
    sessionStatuses,
  } = useChatStore(
    useShallow((state) => ({
      chatHistoryItems: state.chatHistoryItems,
      chatHistoryPagination: state.chatHistoryPagination,
      chatHistoryLoading: state.chatHistoryLoading,
      chatHistoryError: state.chatHistoryError,
      chatHistorySourceFilter: state.chatHistorySourceFilter,
      chatHistorySearchKeyword: state.chatHistorySearchKeyword,
      chatHistoryAvailableSources: state.chatHistoryAvailableSources,
      loadChatHistory: state.loadChatHistory,
      loadMoreChatHistory: state.loadMoreChatHistory,
      setChatHistorySourceFilter: state.setChatHistorySourceFilter,
      setChatHistorySearchKeyword: state.setChatHistorySearchKeyword,
      activeChatId: state.chatId,
      isActiveLoading: state.loading,
      sessionStatuses: state.sessionStatuses,
    })),
  );

  const sentinelRef = useRef<HTMLDivElement>(null);
  const search = useHistorySearch(chatHistorySearchKeyword, setChatHistorySearchKeyword);
  const projectFilter = useProjectStore((state) => state.activeFilter);
  const actions = useChatActions(t);
  const batch = useBatchMode(chatHistoryItems, t);

  const handleOpenInNewWindow = useCallback(async (chatId: string) => {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('open_session_window', { sessionId: chatId });
    } catch (err) {
      console.error('Failed to open session in new window:', err);
    }
  }, []);

  const sessionDragEnabled = isTauriRuntime();
  const handleSessionDragStart = useCallback((chat: ChatItem, event: DragEvent<HTMLElement>) => {
    createPriorChatDragStartHandler({ id: chat.id, title: chat.title })(event);
  }, []);

  const handleFork = useCallback(async (chatId: string) => {
    try {
      const [{ forkConversation }, { default: useWorkspaceStore }, { showI18nToast }] = await Promise.all([
        import('@/services/fork-api'),
        import('@/store/useWorkspaceStore'),
        import('@/services/i18nToastService'),
      ]);
      const response = await forkConversation(chatId, -1);
      if (response.success && response.data.new_chat_id) {
        showI18nToast('chat.fork.success', undefined, { type: 'success' });
        useWorkspaceStore.getState().addPane(response.data.new_chat_id);
      } else {
        showI18nToast('chat.fork.failed', undefined, { type: 'error' });
      }
    } catch (e) {
      console.error('[SidebarFork]', e);
    }
  }, []);

  // Starts the history over from the first page when the sidebar mounts and whenever the project filter changes: the
  // list the store still holds may belong to another project. It is declared before the effect below so that its
  // request is already in flight when that one looks, instead of both asking the server for the same page.
  useEffect(() => {
    useChatStore.setState({
      chatHistoryItems: [],
      chatHistoryPagination: null,
      chatHistoryLoading: false,
      chatHistoryError: null,
    });
    loadChatHistory(1, 20);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectFilter]);

  // Fills a list that has become empty once the sidebar is expanded, but not while a login token is still in the URL.
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.has('token')) {
        return;
      }
    }

    if (isExpanded && chatHistoryItems.length === 0) {
      loadChatHistory(1, 20);
    }
  }, [isExpanded, loadChatHistory, chatHistoryItems.length]);

  const { batchMode, handleExitBatchMode } = batch;
  useEffect(() => {
    if (!batchMode) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleExitBatchMode();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [batchMode, handleExitBatchMode]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && chatHistoryPagination?.has_next && !chatHistoryLoading) {
          loadMoreChatHistory();
        }
      },
      { rootMargin: '100px' },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [chatHistoryPagination, chatHistoryLoading, loadMoreChatHistory]);

  const appLocale = useLocale();
  const formatTime = useMemo(() => (date: Date) => formatRelativeTime(date.toISOString(), appLocale), [appLocale]);

  const handleSourceFilter = useCallback(
    (source: string | null) => {
      setChatHistorySourceFilter(source === chatHistorySourceFilter ? null : source);
    },
    [chatHistorySourceFilter, setChatHistorySourceFilter],
  );

  const pinnedChats = useMemo(
    () => chatHistoryItems.filter((c) => c.isPinned).sort((a, b) => (a.pinOrder ?? 0) - (b.pinOrder ?? 0)),
    [chatHistoryItems],
  );

  const unpinnedChats = useMemo(() => chatHistoryItems.filter((c) => !c.isPinned), [chatHistoryItems]);

  const dateGroups = useMemo(() => groupChatsByDate(unpinnedChats), [unpinnedChats]);
  const { collapsed, toggle: toggleGroup } = useCollapsedGroups();

  const rowProps = (chat: ChatItem): HistoryRowProps => ({
    chat,
    isMobile,
    isActive: activeChatId === chat.id,
    isGenerating: (isActiveLoading && activeChatId === chat.id) || sessionStatuses[chat.id] === 'generating',
    sessionStatus: sessionStatuses[chat.id] as 'generating' | 'awaiting_approval' | undefined,
    renameId: actions.renameId,
    renameValue: actions.renameValue,
    exportingId: actions.exportingId,
    formatTime,
    onItemClick,
    onRename: actions.handleRename,
    onRenameSubmit: actions.handleRenameSubmit,
    onRenameCancel: actions.handleRenameCancel,
    onRenameValueChange: actions.setRenameValue,
    onDelete: actions.handleDeleteClick,
    onExport: actions.handleExport,
    onOpenInIDE: actions.handleOpenInIDE,
    onShare: actions.handleShare,
    onPin: actions.handlePin,
    onUnpin: actions.handleUnpin,
    onCreateAutomation: actions.handleCreateAutomation,
    onHandoff: actions.handleHandoff,
    onFork: handleFork,
    onOpenInNewWindow: isTauriRuntime() ? handleOpenInNewWindow : undefined,
    onRevealArtifacts: actions.handleRevealArtifacts,
    isRevealingArtifacts: actions.revealingArtifactsChatId === chat.id,
    onCaptureEvalCase: actions.handleOpenCaptureEval,
    sessionDragEnabled,
    onSessionDragStart: sessionDragEnabled ? handleSessionDragStart : undefined,
    t,
  });

  if (!isExpanded) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1 px-2 py-3 lg:py-4">
      <ChatHistoryToolbar
        sources={chatHistoryAvailableSources}
        activeSource={chatHistorySourceFilter}
        onSourceClick={handleSourceFilter}
        search={search}
        appliedKeyword={chatHistorySearchKeyword}
        loading={chatHistoryLoading}
        canEnterBatch={!batch.batchMode && unpinnedChats.length > 1}
        onEnterBatch={batch.handleEnterBatchMode}
        isMobile={isMobile}
      />

      <ProjectBar isMobile={isMobile} />
      <ProjectMilestonePanel />

      {batch.batchMode && (
        <div className="px-2 pb-1">
          <BatchOperationBar
            selectedCount={batch.selectedIds.size}
            totalCount={unpinnedChats.length}
            selectedIds={batch.selectedIds}
            isMobile={isMobile}
            onSelectAll={() => batch.handleSelectAll(unpinnedChats)}
            onDeselectAll={batch.handleDeselectAll}
            onDelete={batch.handleBatchDeleteClick}
            onExit={batch.handleExitBatchMode}
            t={t}
          />
        </div>
      )}

      {chatHistoryError && chatHistoryItems.length === 0 ? (
        <div className="px-2 py-4">
          <div className="flex flex-col items-center justify-center gap-3 py-4">
            <AlertCircle size={isMobile ? 20 : 24} className="text-destructive-text" />
            <p className={cn('text-sm text-destructive-text text-center', isMobile && 'text-xs')}>
              {t('common.loadHistoryError')}
            </p>
            <button
              onClick={() => loadChatHistory(1, 20)}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 text-sm rounded-full',
                'bg-primary/10 text-primary hover:bg-primary/20 transition-colors',
                isMobile && 'text-xs px-2 py-1',
              )}
            >
              <RefreshCw size={isMobile ? 12 : 14} />
              {t('common.retry')}
            </button>
          </div>
        </div>
      ) : chatHistoryLoading && chatHistoryItems.length === 0 ? (
        <div className="px-2 py-4 space-y-2">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="animate-pulse">
              <div className="h-4 bg-black/10 dark:bg-white/10 rounded" />
              <div className="h-3 bg-black/5 dark:bg-white/5 rounded mt-1" />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-1">
          {pinnedChats.length > 0 && <PinnedSection chats={pinnedChats} isMobile={isMobile} rowProps={rowProps} />}

          {dateGroups.map((group) => (
            <DateGroupSection
              key={group.key}
              group={group}
              collapsed={!!collapsed[group.key]}
              onToggle={toggleGroup}
              isMobile={isMobile}
              batchMode={batch.batchMode}
              selectedIds={batch.selectedIds}
              onToggleSelect={batch.handleToggleSelect}
              rowProps={rowProps}
            />
          ))}
        </div>
      )}

      {chatHistoryLoading && chatHistoryItems.length > 0 && (
        <div className="flex justify-center py-2">
          <div className="text-xs text-muted-foreground">{t('common.loading')}</div>
        </div>
      )}

      <div ref={sentinelRef} className="h-px" />

      <ChatHistoryDialogs actions={actions} batch={batch} />
    </div>
  );
});

ChatHistoryList.displayName = 'ChatHistoryList';

export default ChatHistoryList;
