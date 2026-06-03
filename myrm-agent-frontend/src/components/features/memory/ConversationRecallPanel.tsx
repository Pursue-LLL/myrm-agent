'use client';

/**
 * [INPUT]
 * - @/services/chat (POS: Frontend chat and Conversation Recall API client)
 * - next-intl::useTranslations (POS: 多语言国际化钩子)
 *
 * [OUTPUT]
 * - ConversationRecallPanel: Conversation Recall management and restore panel.
 *
 * [POS]
 * Conversation Recall 管理面板。展示可召回/已排除会话，并提供跳转、排除与恢复操作。
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { ArchiveRestore, ExternalLink, Loader2, RefreshCw, SearchX } from 'lucide-react';
import { useRouter } from 'next/navigation';

import { toast } from '@/hooks/useToast';
import { cn } from '@/lib/utils/classnameUtils';
import {
  listConversationRecallEntries,
  updateChatRecallExclusion,
  type ConversationRecallEntry,
  type PaginationInfo,
} from '@/services/chat';

type RecallFilter = 'excluded' | 'active' | 'all';

const FILTERS: RecallFilter[] = ['excluded', 'active', 'all'];
const PAGE_SIZE = 20;

const filterToExcluded = (filter: RecallFilter): boolean | undefined => {
  if (filter === 'excluded') return true;
  if (filter === 'active') return false;
  return undefined;
};

const ConversationRecallPanel = memo(() => {
  const t = useTranslations('memory.conversationRecall');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const router = useRouter();

  const [filter, setFilter] = useState<RecallFilter>('excluded');
  const [entries, setEntries] = useState<ConversationRecallEntry[]>([]);
  const [pagination, setPagination] = useState<PaginationInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busyChatId, setBusyChatId] = useState<string | null>(null);

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }),
    [locale],
  );

  const formatDate = useCallback(
    (value: string | null) => {
      if (!value) return t('unknownDate');
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? t('unknownDate') : dateFormatter.format(date);
    },
    [dateFormatter, t],
  );

  const loadEntries = useCallback(
    async (targetPage: number = 1) => {
      if (targetPage === 1) setLoading(true);
      else setLoadingMore(true);
      try {
        const response = await listConversationRecallEntries({
          excluded: filterToExcluded(filter),
          page: targetPage,
          pageSize: PAGE_SIZE,
        });
        setEntries((current) => (targetPage === 1 ? response.items : [...current, ...response.items]));
        setPagination(response.pagination);
      } catch (error) {
        toast({
          title: t('loadFailed'),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [filter, t],
  );

  useEffect(() => {
    void loadEntries(1);
  }, [loadEntries]);

  const handleSetExcluded = useCallback(
    async (entry: ConversationRecallEntry, excluded: boolean) => {
      setBusyChatId(entry.chat_id);
      try {
        await updateChatRecallExclusion(entry.chat_id, excluded);
        toast({
          title: excluded ? t('excludeSuccess') : t('restoreSuccess'),
          description: excluded ? t('excludeSuccessDesc') : t('restoreSuccessDesc'),
        });
        await loadEntries(1);
      } catch (error) {
        toast({
          title: excluded ? t('excludeFailed') : t('restoreFailed'),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setBusyChatId(null);
      }
    },
    [loadEntries, t],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground">{t('title')}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
        </div>
        <button
          onClick={() => loadEntries(1)}
          disabled={loading}
          title={t('refresh')}
          className={cn(
            'inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/60',
            'text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-1 rounded-xl bg-accent/50 p-1">
        {FILTERS.map((item) => (
          <button
            key={item}
            onClick={() => setFilter(item)}
            className={cn(
              'rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200',
              filter === item ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`filters.${item}`)}
          </button>
        ))}
      </div>

      {loading && entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-14">
          <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
          <p className="mt-3 text-sm text-muted-foreground">{t('loading')}</p>
        </div>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-14 text-center">
          <SearchX className="h-9 w-9 text-muted-foreground/50" />
          <p className="mt-3 text-sm font-medium text-foreground">{t('emptyTitle')}</p>
          <p className="mt-1 max-w-md text-xs text-muted-foreground">{t('emptyDescription')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => {
            const busy = busyChatId === entry.chat_id;
            return (
              <div key={entry.chat_id} className="rounded-lg border border-border/60 bg-background/70 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="max-w-full truncate text-sm font-semibold text-foreground">
                        {entry.title || t('untitled')}
                      </h4>
                      <span className="rounded-full border border-border/60 px-2 py-0.5 text-xs text-muted-foreground">
                        {entry.source}
                      </span>
                      {entry.is_excluded && (
                        <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
                          {t('excludedBadge')}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{formatDate(entry.last_message_at)}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      onClick={() => router.push(`/${entry.chat_id}`)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    >
                      <ExternalLink size={14} />
                      {t('open')}
                    </button>
                    <button
                      onClick={() => handleSetExcluded(entry, !entry.is_excluded)}
                      disabled={busy}
                      className={cn(
                        'inline-flex h-8 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium transition-colors',
                        entry.is_excluded
                          ? 'text-primary hover:bg-primary/10'
                          : 'text-muted-foreground hover:bg-destructive/10 hover:text-destructive',
                        'disabled:cursor-not-allowed disabled:opacity-50',
                      )}
                    >
                      {busy ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : entry.is_excluded ? (
                        <ArchiveRestore size={14} />
                      ) : (
                        <SearchX size={14} />
                      )}
                      {entry.is_excluded ? t('restore') : t('exclude')}
                    </button>
                  </div>
                </div>
                <p className="mt-3 line-clamp-2 text-sm text-foreground/80">{entry.snippet || t('emptySnippet')}</p>
                {entry.summary && <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{entry.summary}</p>}
              </div>
            );
          })}
        </div>
      )}

      {pagination?.has_next && (
        <div className="flex justify-center pt-2">
          <button
            onClick={() => loadEntries((pagination.page ?? 1) + 1)}
            disabled={loadingMore}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg border border-border/60 px-5 py-2.5',
              'text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            {loadingMore && <Loader2 size={14} className="animate-spin" />}
            {tCommon('loadMore')}
          </button>
        </div>
      )}
    </div>
  );
});

ConversationRecallPanel.displayName = 'ConversationRecallPanel';

export default ConversationRecallPanel;
