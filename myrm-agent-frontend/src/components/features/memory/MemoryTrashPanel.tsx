'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconLoader, IconTrash } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type { Memory } from '@/store/memory';
import { MemoryTypeIcon } from '@/components/features/memory';

interface MemoryTrashPanelProps {
  memories: Memory[];
  loading: boolean;
  pagination: { has_next: boolean; total: number } | null;
  onRestore: (id: string) => Promise<void>;
  onPurge: (id: string) => Promise<void>;
  onLoadMore: () => void;
}

const MemoryTrashPanel = memo(function MemoryTrashPanel({
  memories,
  loading,
  pagination,
  onRestore,
  onPurge,
  onLoadMore,
}: MemoryTrashPanelProps) {
  const t = useTranslations('memory');
  const tCommon = useTranslations('common');

  if (loading && memories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <IconLoader className="h-8 w-8 animate-spin text-primary/50" />
        <p className="mt-3 text-sm text-muted-foreground">{t('loading')}</p>
      </div>
    );
  }

  if (memories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="relative">
          <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full" />
          <div className="relative bg-accent/50 p-4 rounded-2xl">
            <IconTrash className="h-10 w-10 text-muted-foreground/50" />
          </div>
        </div>
        <p className="mt-4 text-sm font-medium text-foreground">{t('trash.empty')}</p>
        <p className="mt-1 text-xs text-muted-foreground">{t('trash.emptyDesc')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('trash.autoDeleteHint')}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {memories.map((mem) => {
          const archivedAt = mem.metadata?.archived_at as string | undefined;
          const expiresAt = mem.metadata?.archive_expires_at as string | undefined;
          return (
            <div
              key={mem.id}
              className={cn(
                'group rounded-xl border border-border/50 p-4',
                'bg-accent/20 hover:bg-accent/40 transition-colors duration-200',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1.5">
                    <MemoryTypeIcon type={mem.memory_type} size={14} />
                    <span className="text-xs font-medium text-muted-foreground">{t(`types.${mem.memory_type}`)}</span>
                  </div>
                  <p className="text-sm text-foreground line-clamp-3">{mem.content}</p>
                  {archivedAt && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {t('trash.archivedAt')}: {new Date(archivedAt).toLocaleString()}
                    </p>
                  )}
                  {expiresAt && (
                    <p className="text-xs text-muted-foreground">
                      {t('trash.expiresAt')}: {new Date(expiresAt).toLocaleString()}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  <button
                    onClick={() => onRestore(mem.id)}
                    className={cn(
                      'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
                      'bg-primary/10 text-primary hover:bg-primary/20',
                    )}
                  >
                    {t('trash.restore')}
                  </button>
                  <button
                    onClick={() => onPurge(mem.id)}
                    className={cn(
                      'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
                      'bg-destructive/10 text-destructive hover:bg-destructive/20',
                    )}
                  >
                    {t('trash.permanentDelete')}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {pagination?.has_next && (
        <div className="flex justify-center pt-4">
          <button
            onClick={onLoadMore}
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

export default MemoryTrashPanel;
