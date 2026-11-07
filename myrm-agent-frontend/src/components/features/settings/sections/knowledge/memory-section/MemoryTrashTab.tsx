'use client';

/**
 * [INPUT] @/store/memory (POS: 归档记忆与分页), MemoryTrashPanel (POS: 回收站面板)
 * [OUTPUT] MemoryTrashTab: “回收站”标签页，把还原 / 彻底删除 / 加载更多接到 store 并给出结果提示
 * [POS] 已删记忆的恢复入口：还原与彻底删除各自成功 / 失败都有提示；仅在还有下一页时才请求更多归档记忆。
 */

import { useTranslations } from 'next-intl';
import MemoryTrashPanel from '@/components/features/memory/settings/MemoryTrashPanel';
import { toast } from '@/hooks/shared/useToast';
import { useMemoryStore } from '@/store/memory';

export function MemoryTrashTab() {
  const t = useTranslations('memory');
  const archivedMemories = useMemoryStore((state) => state.archivedMemories);
  const archivedLoading = useMemoryStore((state) => state.archivedLoading);
  const archivedPagination = useMemoryStore((state) => state.archivedPagination);
  const fetchArchivedMemories = useMemoryStore((state) => state.fetchArchivedMemories);
  const restoreMemory = useMemoryStore((state) => state.restoreMemory);
  const purgeMemory = useMemoryStore((state) => state.purgeMemory);

  return (
    <MemoryTrashPanel
      memories={archivedMemories}
      loading={archivedLoading}
      pagination={archivedPagination}
      onRestore={async (id) => {
        try {
          await restoreMemory(id);
          toast({ title: t('trash.restoreSuccess') });
        } catch {
          toast({ title: t('trash.restoreFailed'), variant: 'destructive' });
        }
      }}
      onPurge={async (id) => {
        try {
          await purgeMemory(id);
          toast({ title: t('trash.purgeSuccess') });
        } catch {
          toast({ title: t('trash.purgeFailed'), variant: 'destructive' });
        }
      }}
      onLoadMore={() => {
        if (archivedPagination?.has_next) {
          void fetchArchivedMemories(archivedPagination.page + 1);
        }
      }}
    />
  );
}
