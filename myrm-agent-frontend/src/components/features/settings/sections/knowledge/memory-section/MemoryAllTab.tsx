'use client';

/**
 * [INPUT] @/store/memory (POS: 记忆列表与分页), ./MemoryListFilters (POS: 筛选控件), ./useMemoryActions::MemoryActions (POS: 单条记忆操作), MemoryCard (POS: 记忆卡片)
 * [OUTPUT] MemoryAllTab: “全部”标签页（筛选控件 + 加载中 / 空态 / 记忆卡片网格 + 加载更多）
 * [POS] 已确认记忆的浏览页：卡片点击、编辑与各类操作通过回调交给父级；首屏加载中且无数据时显示加载态，加载更多期间按钮禁用。
 */

import { useTranslations } from 'next-intl';
import { IconInbox, IconLoader } from '@/components/features/icons/PremiumIcons';
import MemoryCard from '@/components/features/memory/cards/MemoryCard';
import { cn } from '@/lib/utils/classnameUtils';
import type { TagStatsItem } from '@/services/memory';
import { useMemoryStore, type Memory } from '@/store/memory';
import { MemoryListFilters } from './MemoryListFilters';
import type { MemoryActions } from './useMemoryActions';

interface MemoryAllTabProps {
  searchInput: string;
  onSearchInputChange: (value: string) => void;
  availableTags: TagStatsItem[];
  actions: MemoryActions;
  onOpenDetail: (memory: Memory) => void;
  onEdit: (memory: Memory) => void;
}

export function MemoryAllTab({
  searchInput,
  onSearchInputChange,
  availableTags,
  actions,
  onOpenDetail,
  onEdit,
}: MemoryAllTabProps) {
  const t = useTranslations('memory');
  const tCommon = useTranslations('common');
  const memories = useMemoryStore((state) => state.memories);
  const memoriesLoading = useMemoryStore((state) => state.memoriesLoading);
  const memoryPagination = useMemoryStore((state) => state.memoryPagination);
  const loadMoreMemories = useMemoryStore((state) => state.loadMoreMemories);

  return (
    <div className="space-y-4">
      <MemoryListFilters
        searchInput={searchInput}
        onSearchInputChange={onSearchInputChange}
        availableTags={availableTags}
      />

      {memoriesLoading && memories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12">
          <IconLoader className="h-8 w-8 animate-spin text-primary/50" />
          <p className="mt-3 text-sm text-muted-foreground">{t('loading')}</p>
        </div>
      ) : memories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="relative">
            <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full" />
            <div className="relative bg-accent/50 p-4 rounded-2xl">
              <IconInbox className="h-10 w-10 text-muted-foreground/50" />
            </div>
          </div>
          <p className="mt-4 text-sm font-medium text-foreground">{t('noMemories')}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t('noMemoriesDesc')}</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {memories.map((memory) => (
              <MemoryCard
                key={memory.id}
                memory={memory}
                variant="confirmed"
                onClick={() => onOpenDetail(memory)}
                onEdit={() => onEdit(memory)}
                onDelete={(permanent) => actions.handleDelete(memory.id, memory.memory_type, permanent)}
                onToggleDisable={() => actions.handleToggleDisable(memory)}
                onChatFromMemory={() => actions.handleChatFromMemory(memory)}
                onToggleProtect={(nextLocked) => actions.handleToggleProtect(memory, nextLocked)}
              />
            ))}
          </div>
          {memoryPagination?.has_next && (
            <div className="flex justify-center pt-4">
              <button
                onClick={loadMoreMemories}
                disabled={memoriesLoading}
                className={cn(
                  'flex items-center gap-2 px-6 py-2.5 rounded-lg',
                  'text-sm font-medium transition-all duration-200',
                  'border border-border/50 hover:border-border',
                  'text-muted-foreground hover:text-foreground',
                  'hover:bg-accent',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {memoriesLoading ? (
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
        </>
      )}
    </div>
  );
}
