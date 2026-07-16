'use client';

import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { formatDistanceToNow } from 'date-fns';
import { zhCN, enUS } from 'date-fns/locale';
import { AlertCircle, RefreshCw, Pin, ChevronDown, ListChecks, Loader2, Search, X } from 'lucide-react';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { useCallback, useEffect, memo, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable';
import { ChatHistoryRow, SortablePinnedRow } from './ChatHistoryRow';
import CronJobCreateDialog from '@/components/features/cron/CronJobCreateDialog';
import { HandoffDialog } from './HandoffDialog';
import { ShareConversationDialog } from './ShareConversationDialog';
import { groupChatsByDate, useCollapsedGroups } from './dateGroupUtils';
import BatchOperationBar from './BatchOperationBar';
import ProjectBar from './ProjectBar';
import ProjectMilestonePanel from './ProjectMilestonePanel';
import { useBatchMode } from './useBatchMode';
import { useChatActions } from './useChatActions';
import { useProjectStore } from '@/store/useProjectStore';
import { isTauriRuntime } from '@/lib/deploy-mode';

interface ChatHistoryListProps {
  isExpanded: boolean;
  currentChatId?: string;
  isMobile?: boolean;
  onItemClick?: () => void;
}

const ChatHistoryList = memo<ChatHistoryListProps>(({ isExpanded, currentChatId, isMobile = false, onItemClick }) => {
  const t = useTranslations();

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
    chatId: activeChatId,
    loading: isActiveLoading,
    sessionStatuses,
  } = useChatStore();

  const sentinelRef = useRef<HTMLDivElement>(null);
  const [showSearch, setShowSearch] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [localKeyword, setLocalKeyword] = useState(chatHistorySearchKeyword);
  const { activeFilter: projectFilter } = useProjectStore();
  const actions = useChatActions(chatHistoryItems, t);
  const batch = useBatchMode(chatHistoryItems, t);

  const handleOpenInNewWindow = useCallback(async (chatId: string) => {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('open_session_window', { sessionId: chatId });
    } catch (err) {
      console.error('Failed to open session in new window:', err);
    }
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

  useEffect(() => {
    if (!batch.batchMode) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') batch.handleExitBatchMode();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [batch.batchMode, batch.handleExitBatchMode]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

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

  const formatTime = useMemo(() => {
    const locale = typeof window !== 'undefined' && window.navigator.language.startsWith('zh') ? zhCN : enUS;

    return (date: Date) =>
      formatDistanceToNow(date, {
        addSuffix: true,
        locale,
      });
  }, []);

  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, []);

  const handleSearchChange = useCallback(
    (value: string) => {
      setLocalKeyword(value);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(() => {
        setChatHistorySearchKeyword(value);
      }, 300);
    },
    [setChatHistorySearchKeyword],
  );

  const handleClearSearch = useCallback(() => {
    setLocalKeyword('');
    setChatHistorySearchKeyword('');
    setShowSearch(false);
  }, [setChatHistorySearchKeyword]);

  const handleToggleSearch = useCallback(() => {
    const next = !showSearch;
    setShowSearch(next);
    if (next) {
      requestAnimationFrame(() => searchInputRef.current?.focus());
    } else if (localKeyword) {
      handleClearSearch();
    }
  }, [showSearch, localKeyword, handleClearSearch]);

  const showSourceFilter = chatHistoryAvailableSources.length > 1 || chatHistorySourceFilter !== null;

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

  const { reorderPinnedChats } = useChatStore();

  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      const oldIdx = pinnedChats.findIndex((c) => c.id === active.id);
      const newIdx = pinnedChats.findIndex((c) => c.id === over.id);
      if (oldIdx === -1 || newIdx === -1) return;
      const reordered = arrayMove(pinnedChats, oldIdx, newIdx);
      reorderPinnedChats(reordered.map((c) => c.id));
    },
    [pinnedChats, reorderPinnedChats],
  );

  const rowProps = (chat: ChatItem) => ({
    chat,
    isMobile,
    isActive: currentChatId === chat.id,
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
    onShare: actions.handleShare,
    onPin: actions.handlePin,
    onUnpin: actions.handleUnpin,
    onCreateAutomation: actions.handleCreateAutomation,
    onHandoff: actions.handleHandoff,
    onFork: handleFork,
    onOpenInNewWindow: isTauriRuntime() ? handleOpenInNewWindow : undefined,
    t,
  });

  if (!isExpanded) return null;

  return (
    <div className="flex flex-col gap-1 px-2 py-3 lg:py-4">
      <div className="flex items-center justify-between px-2 pb-1">
        {showSourceFilter ? (
          <div className="flex items-center gap-0.5">
            {chatHistoryAvailableSources.map((source) => (
              <button
                key={source}
                onClick={() => handleSourceFilter(source)}
                title={source}
                className={cn(
                  'p-0.5 rounded transition-all',
                  chatHistorySourceFilter === source
                    ? 'bg-primary/15 ring-1 ring-accent-warm/35 shadow-brand'
                    : 'opacity-50 hover:opacity-100',
                )}
              >
                <ChannelIcon channelId={source} size={12} />
              </button>
            ))}
          </div>
        ) : (
          <div />
        )}
        <div className="flex items-center gap-0.5">
          <button
            onClick={handleToggleSearch}
            className={cn(
              'p-1 rounded transition-colors',
              showSearch || chatHistorySearchKeyword
                ? 'bg-primary/15 text-primary'
                : 'hover:bg-black/5 dark:hover:bg-white/5',
            )}
            title={t('common.search')}
          >
            <Search size={14} className="text-muted-foreground" />
          </button>
          {!batch.batchMode && unpinnedChats.length > 1 && (
            <button
              onClick={batch.handleEnterBatchMode}
              className="p-1 rounded hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
              title={t('chat.batch.enter')}
            >
              <ListChecks size={14} className="text-muted-foreground" />
            </button>
          )}
        </div>
      </div>

      {showSearch && (
        <div className="px-2 pb-1">
          <div className="relative">
            {chatHistoryLoading && localKeyword ? (
              <Loader2 size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-primary animate-spin pointer-events-none" />
            ) : (
              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            )}
            <input
              ref={searchInputRef}
              type="text"
              value={localKeyword}
              onChange={(e) => handleSearchChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Escape') handleClearSearch(); }}
              placeholder={t('common.search')}
              className={cn(
                'w-full pl-7 pr-7 py-1.5 text-xs rounded-md border border-border bg-background',
                'placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/30',
              )}
            />
            {localKeyword && (
              <button
                onClick={handleClearSearch}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/5"
              >
                <X size={12} className="text-muted-foreground" />
              </button>
            )}
          </div>
        </div>
      )}

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
            <AlertCircle size={isMobile ? 20 : 24} className="text-destructive/70" />
            <p className={cn('text-sm text-destructive/80 text-center', isMobile && 'text-xs')}>
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
          {pinnedChats.length > 0 && (
            <>
              <div className="flex items-center gap-1.5 px-2 py-1">
                <Pin size={10} className="text-primary/60" />
                <span
                  className={cn(
                    'text-[10px] font-medium text-primary/60 uppercase tracking-wider',
                    isMobile && 'text-[9px]',
                  )}
                >
                  {t('chat.pin.section')}
                </span>
              </div>
              <DndContext sensors={dndSensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={pinnedChats.map((c) => c.id)} strategy={verticalListSortingStrategy}>
                  {pinnedChats.map((chat, idx) => (
                    <SortablePinnedRow key={chat.id} pinIndex={idx + 1} {...rowProps(chat)} />
                  ))}
                </SortableContext>
              </DndContext>
              <div className="mx-2 my-1 border-t border-black/5 dark:border-white/5" />
            </>
          )}

          {dateGroups.map((group) => {
            const isCollapsed = !!collapsed[group.key];
            return (
              <div key={group.key}>
                <button
                  onClick={() => toggleGroup(group.key)}
                  className={cn(
                    'flex items-center gap-1.5 w-full px-2 py-1 cursor-pointer select-none',
                    'hover:bg-black/3 dark:hover:bg-white/3 rounded transition-colors',
                  )}
                >
                  <ChevronDown
                    size={10}
                    className={cn(
                      'text-black/40 dark:text-white/40 flex-shrink-0 transition-transform duration-200',
                      isCollapsed && '-rotate-90',
                    )}
                  />
                  <span
                    className={cn(
                      'text-[10px] font-medium text-black/50 dark:text-white/50 uppercase tracking-wider',
                      isMobile && 'text-[9px]',
                    )}
                  >
                    {t(`chat.dateGroup.${group.key}` as Parameters<typeof t>[0])}
                  </span>
                </button>
                <div
                  className="grid transition-[grid-template-rows] duration-200 ease-out"
                  style={{ gridTemplateRows: isCollapsed ? '0fr' : '1fr' }}
                >
                  <div className="overflow-hidden">
                    {group.items.map((chat) => (
                      <ChatHistoryRow
                        key={chat.id}
                        batchMode={batch.batchMode}
                        isSelected={batch.selectedIds.has(chat.id)}
                        onToggleSelect={batch.handleToggleSelect}
                        {...rowProps(chat)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {chatHistoryLoading && chatHistoryItems.length > 0 && (
        <div className="flex justify-center py-2">
          <div className="text-xs text-muted-foreground">{t('common.loading')}</div>
        </div>
      )}

      <div ref={sentinelRef} className="h-px" />

      <ConfirmDialog
        open={actions.deleteDialogOpen}
        onOpenChange={actions.setDeleteDialogOpen}
        title={t('chat.deleteChat.title')}
        description={t('chat.deleteChat.description')}
        confirmText={t('chat.deleteChat.confirm')}
        cancelText={t('chat.deleteChat.cancel')}
        loadingText={t('chat.deleteChat.deleting')}
        variant="destructive"
        onConfirm={actions.handleDeleteConfirm}
      />

      <ConfirmDialog
        open={batch.batchDeleteDialogOpen}
        onOpenChange={batch.setBatchDeleteDialogOpen}
        title={t('chat.batch.confirmTitle', { count: batch.selectedIds.size })}
        description={t('chat.batch.confirmDesc')}
        confirmText={t('chat.batch.confirmAction')}
        cancelText={t('chat.deleteChat.cancel')}
        loadingText={t('chat.batch.deleting')}
        variant="destructive"
        onConfirm={batch.handleBatchDeleteConfirm}
      />

      <CronJobCreateDialog
        open={actions.automationDialogOpen}
        onOpenChange={actions.setAutomationDialogOpen}
        presetChatId={actions.automationChatId}
        presetChatTitle={actions.automationChatTitle}
      />

      {actions.handoffChatId && (
        <HandoffDialog
          open={actions.handoffDialogOpen}
          onOpenChange={actions.setHandoffDialogOpen}
          chatId={actions.handoffChatId}
          chatTitle={actions.handoffChatTitle}
          currentSource={actions.handoffChatSource}
        />
      )}

      <ShareConversationDialog
        open={actions.shareDialogOpen}
        onOpenChange={actions.setShareDialogOpen}
        shareUrl={actions.shareUrl}
        expiresAt={actions.shareExpiresAt}
        loading={actions.shareLoading}
        onCreateLink={actions.handleShareCreate}
        onRevoke={actions.handleShareRevoke}
      />
    </div>
  );
});

ChatHistoryList.displayName = 'ChatHistoryList';

export default ChatHistoryList;
