'use client';

/**
 * [INPUT] @/store/memory (POS: 筛选 / 排序状态), @/services/memory::TagStatsItem (POS: 标签统计), MemoryTypeIcon (POS: 类型图标)
 * [OUTPUT] MemoryListFilters: “全部”页的搜索框、类型筛选、排序、标签筛选
 * [POS] 记忆列表的筛选控件组：搜索文本由父级持有（跨标签页保留），类型 / 排序 / 标签直接读写 store；返回 Fragment，由 MemoryAllTab 统一排布间距。
 */

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { IconArrowDown, IconArrowUp, IconArrowUpDown, IconSearch } from '@/components/features/icons/PremiumIcons';
import MemoryTypeIcon from '@/components/features/memory/cards/MemoryTypeIcon';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemorySortBy, TagStatsItem } from '@/services/memory';
import { useMemoryStore, type MemoryType } from '@/store/memory';

const MEMORY_TYPES: (MemoryType | null)[] = [
  null,
  'profile',
  'semantic',
  'episodic',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
];

const TAG_CHIP_LIMIT = 10;

interface MemoryListFiltersProps {
  searchInput: string;
  onSearchInputChange: (value: string) => void;
  availableTags: TagStatsItem[];
}

export function MemoryListFilters({ searchInput, onSearchInputChange, availableTags }: MemoryListFiltersProps) {
  const t = useTranslations('memory');
  const memoryTypeFilter = useMemoryStore((state) => state.memoryTypeFilter);
  const setMemoryTypeFilter = useMemoryStore((state) => state.setMemoryTypeFilter);
  const memoryTagFilter = useMemoryStore((state) => state.memoryTagFilter);
  const setMemoryTagFilter = useMemoryStore((state) => state.setMemoryTagFilter);
  const memorySortBy = useMemoryStore((state) => state.memorySortBy);
  const setMemorySortBy = useMemoryStore((state) => state.setMemorySortBy);
  const memorySortOrder = useMemoryStore((state) => state.memorySortOrder);
  const setMemorySortOrder = useMemoryStore((state) => state.setMemorySortOrder);

  return (
    <>
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => onSearchInputChange(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className={cn(
              'w-full pl-9 pr-4 py-2.5 rounded-lg',
              'bg-accent/50 border border-border/50',
              'text-sm text-foreground placeholder:text-muted-foreground/50',
              'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
              'transition-all duration-200',
            )}
          />
        </div>
        <div className="flex items-center gap-1 p-1 bg-accent/50 rounded-lg overflow-x-auto">
          {MEMORY_TYPES.map((type) => {
            const button = (
              <button
                key={type ?? 'all'}
                onClick={() => setMemoryTypeFilter(type)}
                className={cn(
                  'px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200',
                  'flex items-center gap-1.5 whitespace-nowrap',
                  memoryTypeFilter === type
                    ? 'bg-background text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {type ? (
                  <>
                    <MemoryTypeIcon type={type} size={12} />
                    <span className="hidden sm:inline">{t(`types.${type}`)}</span>
                  </>
                ) : (
                  t('filterAll')
                )}
              </button>
            );

            if (!type) {
              return button;
            }

            return (
              <Tooltip key={type}>
                <TooltipTrigger asChild>{button}</TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[280px] space-y-1.5">
                  <div className="font-medium text-foreground">{t(`types.${type}`)}</div>
                  <div className="text-muted-foreground">{t(`typeTooltips.${type}.description`)}</div>
                  <div className="text-xs text-muted-foreground/80 pt-1 border-t border-border/50">
                    {t(`typeTooltips.${type}.example`)}
                  </div>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <IconArrowUpDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <select
          value={memorySortBy}
          onChange={(e) => setMemorySortBy(e.target.value as MemorySortBy)}
          className={cn(
            'px-2 py-1.5 rounded-full text-xs font-medium',
            'bg-accent/50 border border-border/50',
            'text-foreground',
            'focus:outline-none focus:ring-2 focus:ring-primary/20',
          )}
        >
          <option value="created_at">{t('createdAt')}</option>
          <option value="updated_at">{t('updatedAt')}</option>
          <option value="importance">{t('importance')}</option>
        </select>
        <button
          onClick={() => setMemorySortOrder(memorySortOrder === 'desc' ? 'asc' : 'desc')}
          className="p-1.5 rounded-full hover:bg-accent transition-colors"
          title={memorySortOrder === 'desc' ? t('sortDescending') : t('sortAscending')}
        >
          {memorySortOrder === 'desc' ? (
            <IconArrowDown className="w-3.5 h-3.5 text-muted-foreground" />
          ) : (
            <IconArrowUp className="w-3.5 h-3.5 text-muted-foreground" />
          )}
        </button>
      </div>

      {availableTags.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground mr-1">{t('tags')}:</span>
          <TagChip active={!memoryTagFilter} onClick={() => setMemoryTagFilter(null)}>
            {t('filterAll')}
          </TagChip>
          {availableTags.slice(0, TAG_CHIP_LIMIT).map(({ tag, count }) => (
            <TagChip
              key={tag}
              active={memoryTagFilter === tag}
              onClick={() => setMemoryTagFilter(memoryTagFilter === tag ? null : tag)}
            >
              {tag}
              <span className="ml-1 opacity-60">{count}</span>
            </TagChip>
          ))}
        </div>
      )}
    </>
  );
}

function TagChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-2 py-1 rounded-full text-[11px] font-medium transition-all',
        active
          ? 'bg-primary/10 text-primary border border-primary/20'
          : 'bg-accent/50 text-muted-foreground border border-transparent hover:bg-accent',
      )}
    >
      {children}
    </button>
  );
}
