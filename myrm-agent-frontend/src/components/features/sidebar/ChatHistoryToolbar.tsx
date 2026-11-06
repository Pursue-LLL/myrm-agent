'use client';

/**
 * [INPUT]
 * - ./useHistorySearch::HistorySearch (POS: 搜索框的开合与输入状态)
 * - @/components/features/settings/sections/integration/channels/ChannelIcon (POS: 来源图标)
 *
 * [OUTPUT]
 * - ChatHistoryToolbar: 会话列表顶部的来源筛选、搜索与批量选择入口，以及展开后的搜索框。
 *
 * [POS]
 * 只渲染不持有状态：来源多于一个或已有筛选时才显示来源芯片（再点一次同一来源由调用方清除筛选）；
 * 搜索钮在搜索框打开或已有关键词时高亮；批量选择钮只在调用方允许时出现；搜索进行中输入框左侧换成转圈。
 */
import { ListChecks, Loader2, Search, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';
import { cn } from '@/lib/utils/classnameUtils';
import type { HistorySearch } from './useHistorySearch';

interface ChatHistoryToolbarProps {
  sources: readonly string[];
  activeSource: string | null;
  onSourceClick: (source: string) => void;
  search: HistorySearch;
  /** The keyword currently applied to the history, which lights the search button even with the field closed. */
  appliedKeyword: string;
  loading: boolean;
  canEnterBatch: boolean;
  onEnterBatch: () => void;
}

export function ChatHistoryToolbar({
  sources,
  activeSource,
  onSourceClick,
  search,
  appliedKeyword,
  loading,
  canEnterBatch,
  onEnterBatch,
}: ChatHistoryToolbarProps) {
  const t = useTranslations();
  const { showSearch, localKeyword, searchInputRef, handleSearchChange, handleClearSearch, handleToggleSearch } =
    search;
  const showSourceFilter = sources.length > 1 || activeSource !== null;

  return (
    <>
      <div className="flex items-center justify-between px-2 pb-1">
        {showSourceFilter ? (
          <div className="flex items-center gap-0.5">
            {sources.map((source) => (
              <button
                key={source}
                onClick={() => onSourceClick(source)}
                title={source}
                className={cn(
                  'p-0.5 rounded transition-all',
                  activeSource === source
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
              showSearch || appliedKeyword ? 'bg-primary/15 text-primary' : 'hover:bg-black/5 dark:hover:bg-white/5',
            )}
            title={t('common.search')}
          >
            <Search size={14} className="text-muted-foreground" />
          </button>
          {canEnterBatch && (
            <button
              onClick={onEnterBatch}
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
            {loading && localKeyword ? (
              <Loader2
                size={12}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-primary animate-spin pointer-events-none"
              />
            ) : (
              <Search
                size={12}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
              />
            )}
            <input
              ref={searchInputRef}
              type="text"
              value={localKeyword}
              onChange={(e) => handleSearchChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  handleClearSearch();
                }
              }}
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
    </>
  );
}
