import { useCallback, useState } from 'react';
import { batchDeleteChats, type ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { toast } from '@/hooks/useToast';
import type { useTranslations } from 'next-intl';

export function useBatchMode(chatHistoryItems: ChatItem[], t: ReturnType<typeof useTranslations>) {
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleteDialogOpen, setBatchDeleteDialogOpen] = useState(false);

  const handleToggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleEnterBatchMode = useCallback(() => {
    setBatchMode(true);
    setSelectedIds(new Set());
  }, []);

  const handleExitBatchMode = useCallback(() => {
    setBatchMode(false);
    setSelectedIds(new Set());
  }, []);

  const handleBatchDeleteClick = useCallback(() => {
    if (selectedIds.size === 0) return;
    setBatchDeleteDialogOpen(true);
  }, [selectedIds.size]);

  const handleBatchDeleteConfirm = useCallback(async () => {
    if (selectedIds.size === 0) return;
    try {
      const ids = Array.from(selectedIds);
      const result = await batchDeleteChats(ids);
      const remaining = chatHistoryItems.filter((c) => !selectedIds.has(c.id));
      useChatStore.getState().setChatHistoryItems(remaining);
      setBatchMode(false);
      setSelectedIds(new Set());
      toast(t('chat.batch.successMessage', { count: result.deleted }), {
        description:
          result.failed > 0 ? t('chat.batch.partialFail', { count: result.failed }) : t('chat.deleteChat.undoHint'),
      });
    } catch (error) {
      console.error('Batch delete failed:', error);
      toast({
        title: t('chat.batch.error'),
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  }, [selectedIds, chatHistoryItems, t]);

  const handleSelectAll = useCallback(
    (unpinnedChats: ChatItem[]) => setSelectedIds(new Set(unpinnedChats.map((c) => c.id))),
    [],
  );

  const handleDeselectAll = useCallback(() => setSelectedIds(new Set()), []);

  return {
    batchMode,
    selectedIds,
    batchDeleteDialogOpen,
    setBatchDeleteDialogOpen,
    handleToggleSelect,
    handleEnterBatchMode,
    handleExitBatchMode,
    handleBatchDeleteClick,
    handleBatchDeleteConfirm,
    handleSelectAll,
    handleDeselectAll,
  };
}
