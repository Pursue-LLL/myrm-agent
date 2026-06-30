'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconLoader, IconTrash } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/useToast';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import type { CascadeInfo, TrashedChatItem } from '@/services/chatTrash';
import { emptyTrash, getCascadeInfo, getTrashedChats, permanentlyDeleteChat, restoreChat } from '@/services/chatTrash';

interface SessionTrashPanelProps {
  onRestored?: () => void;
  onCountChange?: (count: number) => void;
}

const SessionTrashPanel = memo(function SessionTrashPanel({ onRestored, onCountChange }: SessionTrashPanelProps) {
  const t = useTranslations('chat.trash');
  const tCommon = useTranslations('common');

  const [chats, setChats] = useState<TrashedChatItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [total, setTotal] = useState(0);
  const [cascadeInfo, setCascadeInfo] = useState<CascadeInfo | null>(null);
  const cascadeFetchRef = useRef<string | null>(null);

  const fetchTrashed = useCallback(
    async (pageNum: number, append = false) => {
      setLoading(true);
      try {
        const res = await getTrashedChats(pageNum);
        setChats((prev) => (append ? [...prev, ...res.items] : res.items));
        setHasNext(res.pagination.has_next);
        setTotal(res.pagination.total);
        onCountChange?.(res.pagination.total);
      } finally {
        setLoading(false);
      }
    },
    [onCountChange],
  );

  useEffect(() => {
    fetchTrashed(1);
  }, [fetchTrashed]);

  const handleRestore = async (chatId: string) => {
    try {
      await restoreChat(chatId);
      setChats((prev) => prev.filter((c) => c.id !== chatId));
      setTotal((prev) => {
        const newTotal = prev - 1;
        onCountChange?.(newTotal);
        return newTotal;
      });
      onRestored?.();
      toast({ title: t('restored'), variant: 'default' });
    } catch {
      toast({ title: t('restoreFailed'), variant: 'destructive' });
    }
  };

  const handlePermanentDelete = async (chatId: string) => {
    try {
      await permanentlyDeleteChat(chatId);
      setChats((prev) => prev.filter((c) => c.id !== chatId));
      setTotal((prev) => {
        const newTotal = prev - 1;
        onCountChange?.(newTotal);
        return newTotal;
      });
      toast({ title: t('permanentlyDeleted'), variant: 'default' });
    } catch {
      toast({ title: t('deleteFailed'), variant: 'destructive' });
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
        setCascadeInfo({ counts: {}, total: 0 });
      }
    }
    if (!open) {
      cascadeFetchRef.current = null;
      setCascadeInfo(null);
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
      setTotal(0);
      onCountChange?.(0);
      toast({ title: t('emptied'), variant: 'default' });
    } catch {
      toast({ title: t('emptyFailed'), variant: 'destructive' });
    }
  };

  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchTrashed(nextPage, true);
  };

  if (loading && chats.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <IconLoader className="h-8 w-8 animate-spin text-primary/50" />
        <p className="mt-3 text-sm text-muted-foreground">{t('loading')}</p>
      </div>
    );
  }

  if (chats.length === 0) {
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
                'bg-destructive/10 text-destructive hover:bg-destructive/20',
              )}
            >
              {t('emptyAll')} ({total})
            </button>
          }
          title={t('confirmEmptyTitle')}
          description={t('confirmEmptyDesc', { count: total })}
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
              <div className="flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity shrink-0">
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
                        'bg-destructive/10 text-destructive hover:bg-destructive/20',
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
