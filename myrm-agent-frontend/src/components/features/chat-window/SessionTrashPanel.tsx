'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconLoader, IconTrash } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/shared/useToast';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import type { CascadeInfo, TrashedChatItem } from '@/services/chatTrash';
import {
  TRASH_PAGE_SIZE,
  emptyTrash,
  getCascadeInfo,
  getTrashedChats,
  permanentlyDeleteChat,
  restoreChat,
} from '@/services/chatTrash';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

interface SessionTrashPanelProps {
  onRestored?: () => void;
  onCountChange?: (count: number) => void;
}

/** Adds the chats of a freshly read page that the list does not hold yet (all of them when the list is empty). */
function appendNew(current: TrashedChatItem[], incoming: TrashedChatItem[]): TrashedChatItem[] {
  const known = new Set(current.map((chat) => chat.id));
  return [...current, ...incoming.filter((chat) => !known.has(chat.id))];
}

const SessionTrashPanel = memo(function SessionTrashPanel({ onRestored, onCountChange }: SessionTrashPanelProps) {
  const t = useTranslations('chat.trash');
  const tCommon = useTranslations('common');

  const [chats, setChats] = useState<TrashedChatItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [hasNext, setHasNext] = useState(false);
  // Unknown until the first page has been read.
  const [total, setTotal] = useState<number | null>(null);
  const [cascadeInfo, setCascadeInfo] = useState<CascadeInfo | null>(null);
  const cascadeFetchRef = useRef<string | null>(null);
  // Chats with a request in flight: a second click on the same row would only add a request that fails.
  const inFlightRef = useRef(new Set<string>());

  /** Reads `page` into the list. A failed first read shows the error screen; a failed later page only a notice. */
  const fetchTrashed = useCallback(
    async (page: number, loadingMore: boolean) => {
      setLoading(true);
      setLoadFailed(false);
      try {
        const res = await getTrashedChats(page);
        setChats((prev) => appendNew(prev, res.items));
        setHasNext(res.pagination.has_next);
        setTotal(res.pagination.total);
      } catch {
        if (loadingMore) {
          toast({ title: t('loadFailed'), variant: 'destructive' });
        } else {
          setLoadFailed(true);
        }
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchTrashed(1, false);
  }, [fetchTrashed]);

  // Restoring or deleting every loaded chat can leave older ones on the server: read them instead of calling the
  // trash empty.
  useEffect(() => {
    if (!loading && !loadFailed && hasNext && chats.length === 0) {
      void fetchTrashed(1, false);
    }
  }, [loading, loadFailed, hasNext, chats.length, fetchTrashed]);

  // The parent shows the count (badge); it hears about every change from here, once the first read has told it.
  useEffect(() => {
    if (total !== null) {
      onCountChange?.(total);
    }
  }, [total, onCountChange]);

  const removeChat = useCallback((chatId: string) => {
    setChats((prev) => prev.filter((chat) => chat.id !== chatId));
    setTotal((prev) => (prev === null ? prev : prev - 1));
  }, []);

  const handleRestore = async (chatId: string) => {
    if (inFlightRef.current.has(chatId)) {
      return;
    }
    inFlightRef.current.add(chatId);
    try {
      await restoreChat(chatId);
      removeChat(chatId);
      onRestored?.();
      toast({ title: t('restored'), variant: 'default' });
    } catch {
      toast({ title: t('restoreFailed'), variant: 'destructive' });
    } finally {
      inFlightRef.current.delete(chatId);
    }
  };

  const handlePermanentDelete = async (chatId: string) => {
    if (inFlightRef.current.has(chatId)) {
      return;
    }
    inFlightRef.current.add(chatId);
    try {
      await permanentlyDeleteChat(chatId);
      removeChat(chatId);
      toast({ title: t('permanentlyDeleted'), variant: 'default' });
    } catch {
      toast({ title: t('deleteFailed'), variant: 'destructive' });
    } finally {
      inFlightRef.current.delete(chatId);
    }
  };

  const handleDeleteDialogOpen = useCallback(async (open: boolean, chatId: string) => {
    if (open && cascadeFetchRef.current !== chatId) {
      cascadeFetchRef.current = chatId;
      setCascadeInfo(null);
      try {
        const info = await getCascadeInfo(chatId);
        if (cascadeFetchRef.current === chatId) {
          setCascadeInfo(info);
        }
      } catch {
        // The warning is a courtesy: without a count the chat can still be deleted.
      }
    }
    if (!open) {
      // Keeps what the dialog shows while it fades out; the next opening starts from a blank.
      cascadeFetchRef.current = null;
    }
  }, []);

  const getDeleteDescription = (chatTitle: string) => {
    const base = t('confirmDeleteDesc', { title: chatTitle });
    if (cascadeInfo && cascadeInfo.total > 0) {
      return `${base}\n${t('cascadeWarning', { count: cascadeInfo.total })}`;
    }
    return base;
  };

  const handleEmptyTrash = async () => {
    try {
      await emptyTrash();
      setChats([]);
      setHasNext(false);
      setTotal(0);
      toast({ title: t('emptied'), variant: 'default' });
    } catch {
      toast({ title: t('emptyFailed'), variant: 'destructive' });
    }
  };

  // Chats restored or deleted since the last read shift the server's pages: the first chat not yet loaded sits on the
  // page that starts at or before the loaded count, and the overlap is dropped when it is appended.
  const handleLoadMore = () => {
    void fetchTrashed(Math.floor(chats.length / TRASH_PAGE_SIZE) + 1, true);
  };

  if (chats.length === 0) {
    if (loadFailed) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <p className="text-sm text-muted-foreground">{t('loadFailed')}</p>
          <button
            type="button"
            onClick={() => void fetchTrashed(1, false)}
            className={cn(
              'px-4 py-2 rounded-lg text-xs font-medium transition-colors',
              'bg-primary/10 text-primary hover:bg-primary/20',
            )}
          >
            {tCommon('retry')}
          </button>
        </div>
      );
    }
    if (loading || hasNext) {
      return (
        <div className="flex flex-col items-center justify-center py-12">
          <IconLoader className="h-8 w-8 animate-spin text-primary/50" />
          <p className="mt-3 text-sm text-muted-foreground">{t('loading')}</p>
        </div>
      );
    }
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="relative">
          <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full" />
          <div className="relative bg-accent/50 p-4 rounded-2xl">
            <IconTrash className="h-10 w-10 text-muted-foreground/50" />
          </div>
        </div>
        <p className="mt-4 text-sm font-medium text-foreground">{t('empty')}</p>
        <p className="mt-1 text-xs text-muted-foreground">{t('emptyDesc')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{t('autoDeleteHint')}</p>
        <ConfirmDialog
          trigger={
            <button
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                'bg-destructive/10 text-destructive-text hover:bg-destructive/20',
              )}
            >
              {t('emptyAll')} ({total ?? 0})
            </button>
          }
          title={t('confirmEmptyTitle')}
          description={t('confirmEmptyDesc', { count: total ?? 0 })}
          confirmText={t('emptyAll')}
          cancelText={tCommon('cancel')}
          variant="destructive"
          onConfirm={handleEmptyTrash}
        />
      </div>
      <div className="grid grid-cols-1 gap-3">
        {chats.map((chat) => (
          <div
            key={chat.id}
            className={cn(
              'group rounded-xl border border-border/50 p-4',
              'bg-accent/20 hover:bg-accent/40 transition-colors duration-200',
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground truncate">{chat.title || t('untitled')}</p>
                {chat.lastMessage && (
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{chat.lastMessage}</p>
                )}
                {chat.deletedAt && (
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {t('deletedAt')}: {new Date(chat.deletedAt).toLocaleString()}
                  </p>
                )}
              </div>
              <div className={cn('flex items-center gap-1 transition-opacity shrink-0', REVEAL_ON_HOVER)}>
                <button
                  onClick={() => handleRestore(chat.id)}
                  className={cn(
                    'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    'bg-primary/10 text-primary hover:bg-primary/20',
                  )}
                >
                  {t('restore')}
                </button>
                <ConfirmDialog
                  trigger={
                    <button
                      className={cn(
                        'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
                        'bg-destructive/10 text-destructive-text hover:bg-destructive/20',
                      )}
                    >
                      {t('permanentDelete')}
                    </button>
                  }
                  title={t('confirmDeleteTitle')}
                  description={getDeleteDescription(chat.title || t('untitled'))}
                  confirmText={t('permanentDelete')}
                  cancelText={tCommon('cancel')}
                  variant="destructive"
                  onConfirm={() => handlePermanentDelete(chat.id)}
                  onOpenChange={(open) => handleDeleteDialogOpen(open, chat.id)}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
      {hasNext && (
        <div className="flex justify-center pt-4">
          <button
            onClick={handleLoadMore}
            disabled={loading}
            className={cn(
              'flex items-center gap-2 px-6 py-2.5 rounded-lg',
              'text-sm font-medium transition-all duration-200',
              'border border-border/50 hover:border-border',
              'text-muted-foreground hover:text-foreground',
              'hover:bg-accent',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {loading ? (
              <>
                <IconLoader className="w-3.5 h-3.5 animate-spin" />
                {t('loading')}
              </>
            ) : (
              tCommon('loadMore')
            )}
          </button>
        </div>
      )}
    </div>
  );
});

export default SessionTrashPanel;
