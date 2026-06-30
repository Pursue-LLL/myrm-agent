'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, X, CheckCheck, Loader2, Inbox } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useMemoryStore } from '@/store/memory';
import type { ConflictResolution } from '@/store/memory';
import MemoryCard from './MemoryCard';
import ConflictCard from './ConflictCard';
import { toast } from '@/hooks/useToast';

interface PendingMemoryListProps {
  className?: string;
  showBatchActions?: boolean;
}

const PendingMemoryList = memo<PendingMemoryListProps>(({ className, showBatchActions = true }) => {
  const t = useTranslations('memory');
  const {
    pendingMemories,
    pendingLoading,
    pendingError,
    selectedPendingIds,
    toggleSelectPending,
    selectAllPending,
    batchApprove,
    batchReject,
    approveMemory,
    rejectMemory,
    fetchPendingMemories,
    conflicts,
    conflictsLoading,
    fetchConflicts,
    resolveConflict,
  } = useMemoryStore();

  useEffect(() => {
    fetchConflicts();
  }, [fetchConflicts]);

  const selectedCount = selectedPendingIds.size;
  const allSelected = pendingMemories.length > 0 && selectedCount === pendingMemories.length;
  const [isProcessing, setIsProcessing] = useState(false);

  const handleBatchApprove = useCallback(async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      await batchApprove();
      toast({
        title: t('batchApproveSuccess'),
        description: t('batchApproveSuccessDesc', { count: selectedCount }),
      });
    } catch (error) {
      toast({
        title: t('batchApproveFailed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsProcessing(false);
    }
  }, [batchApprove, selectedCount, t, isProcessing]);

  const handleBatchReject = useCallback(async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      await batchReject();
      toast({
        title: t('batchRejectSuccess'),
        description: t('batchRejectSuccessDesc', { count: selectedCount }),
      });
    } catch (error) {
      toast({
        title: t('batchRejectFailed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsProcessing(false);
    }
  }, [batchReject, selectedCount, t, isProcessing]);

  const handleApprove = useCallback(
    async (id: string, editedContent?: string) => {
      try {
        await approveMemory(id, editedContent);
        toast({
          title: t('approveSuccess'),
          description: t('approveSuccessDesc'),
        });
      } catch (error) {
        toast({
          title: t('approveFailed'),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      }
    },
    [approveMemory, t],
  );

  const handleReject = useCallback(
    async (id: string) => {
      try {
        await rejectMemory(id);
        toast({
          title: t('rejectSuccess'),
          description: t('rejectSuccessDesc'),
        });
      } catch (error) {
        toast({
          title: t('rejectFailed'),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      }
    },
    [rejectMemory, t],
  );

  const handleResolveConflict = useCallback(
    async (id: string, resolution: ConflictResolution, mergedContent?: string) => {
      try {
        await resolveConflict(id, resolution, mergedContent);
        toast({
          title: t('conflict.resolveSuccess', { defaultMessage: '冲突已解决' }),
          description: t('conflict.resolveSuccessDesc', { defaultMessage: '记忆冲突已成功处理' }),
        });
      } catch (error) {
        toast({
          title: t('conflict.resolveFailed', { defaultMessage: '解决失败' }),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      }
    },
    [resolveConflict, t],
  );

  // 加载状态
  if (pendingLoading && pendingMemories.length === 0) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12', className)}>
        <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
        <p className="mt-3 text-sm text-muted-foreground">{t('loading')}</p>
      </div>
    );
  }

  // 错误状态
  if (pendingError) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12', className)}>
        <p className="text-sm text-destructive">{pendingError}</p>
        <button onClick={() => fetchPendingMemories()} className="mt-3 text-sm text-primary hover:underline">
          {t('retry')}
        </button>
      </div>
    );
  }

  const hasConflicts = conflicts.length > 0;

  // 空状态 (no pending and no conflicts)
  if (pendingMemories.length === 0 && !hasConflicts) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-16', className)}>
        <div className="relative">
          <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full" />
          <div className="relative bg-accent/50 p-4 rounded-2xl">
            <Inbox className="h-10 w-10 text-muted-foreground/50" />
          </div>
        </div>
        <p className="mt-4 text-sm font-medium text-foreground">{t('noPendingMemories')}</p>
        <p className="mt-1 text-xs text-muted-foreground">{t('noPendingMemoriesDesc')}</p>
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* 批量操作栏 */}
      {showBatchActions && (
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-3">
            <button
              onClick={selectAllPending}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm',
                'transition-colors duration-200',
                'hover:bg-accent',
                allSelected ? 'text-primary' : 'text-muted-foreground',
              )}
            >
              <CheckCheck size={16} />
              {allSelected ? t('deselectAll') : t('selectAll')}
            </button>

            {selectedCount > 0 && (
              <span className="text-xs text-muted-foreground">{t('selectedCount', { count: selectedCount })}</span>
            )}
          </div>

          {selectedCount > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={handleBatchReject}
                disabled={isProcessing}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                  'transition-colors duration-200',
                  'border border-destructive/30 hover:border-destructive/50',
                  'text-destructive hover:bg-destructive/5',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {isProcessing ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
                {t('batchReject')}
              </button>
              <button
                onClick={handleBatchApprove}
                disabled={isProcessing}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                  'transition-colors duration-200',
                  'bg-primary/10 hover:bg-primary/20',
                  'text-primary border border-primary/20 hover:border-primary/40',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {isProcessing ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                {t('batchAccept')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* 冲突区域 */}
      {hasConflicts && (
        <div className="space-y-3">
          {conflicts.map((conflict) => (
            <ConflictCard
              key={conflict.id}
              conflict={conflict}
              onResolve={handleResolveConflict}
            />
          ))}
        </div>
      )}

      {/* 记忆列表 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {pendingMemories.map((memory) => (
          <MemoryCard
            key={memory.id}
            memory={memory}
            variant="pending"
            selected={selectedPendingIds.has(memory.id)}
            onSelect={() => toggleSelectPending(memory.id)}
            onApprove={(editedContent) => handleApprove(memory.id, editedContent)}
            onReject={() => handleReject(memory.id)}
          />
        ))}
      </div>
    </div>
  );
});

PendingMemoryList.displayName = 'PendingMemoryList';

export default PendingMemoryList;
