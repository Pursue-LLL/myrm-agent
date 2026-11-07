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
 * 只渲染不持有状态：来源多于一个或已有筛选时才显示来源芯片（再点一次同一来源由调用方清除筛选，`aria-pressed` 报告当前筛选）；
 * 搜索钮在搜索框打开或已有关键词时高亮；批量选择钮只在调用方允许时出现；搜索进行中输入框左侧换成转圈。
 * 点击目标：指针设备不小于 24px（WCAG 2.5.8），手机用手指尺寸（按钮 44px、芯片 40px）；
 * 来源多到一行放不下时芯片换行，右侧按钮贴着第一行，不缩小目标也不被挤出屏幕；
 * 手机上输入框用 16px 字号，避免 iOS 聚焦时整页被放大。
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
  isMobile: boolean;
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
  isMobile,
}: ChatHistoryToolbarProps) {
  const t = useTranslations();
  const { showSearch, localKeyword, searchInputRef, handleSearchChange, handleClearSearch, handleToggleSearch } =
    search;
  const showSourceFilter = sources.length > 1 || activeSource !== null;
  const actionButton = cn(
    'flex items-center justify-center rounded-lg transition-colors',
    isMobile ? 'size-11' : 'size-7',
  );
  const actionIconSize = isMobile ? 18 : 14;
  const fieldIconSize = isMobile ? 16 : 12;

  return (
    <>
      <div className="flex items-start justify-between px-2 pb-1">
        {showSourceFilter ? (
          <div className="flex flex-wrap items-center gap-0.5 self-center">
            {sources.map((source) => (
              <button
                key={source}
                onClick={() => onSourceClick(source)}
                title={source}
                aria-pressed={activeSource === source}
                className={cn(
                  'flex items-center justify-center rounded-lg transition-all',
                  isMobile ? 'size-10' : 'size-6',
                  activeSource === source
                    ? 'bg-primary/15 ring-1 ring-accent-warm/35 shadow-brand'
                    : 'opacity-50 hover:opacity-100',
                )}
              >
                <ChannelIcon channelId={source} size={actionIconSize} />
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
              actionButton,
              showSearch || appliedKeyword ? 'bg-primary/15 text-primary' : 'hover:bg-black/5 dark:hover:bg-white/5',
            )}
            title={t('common.search')}
          >
            <Search size={actionIconSize} className="text-muted-foreground" />
          </button>
          {canEnterBatch && (
            <button
              onClick={onEnterBatch}
              className={cn(actionButton, 'hover:bg-black/5 dark:hover:bg-white/5')}
              title={t('chat.batch.enter')}
            >
              <ListChecks size={actionIconSize} className="text-muted-foreground" />
            </button>
          )}
        </div>
      </div>

      {showSearch && (
        <div className="px-2 pb-1">
          <div className="relative">
            {loading && localKeyword ? (
              <Loader2
                size={fieldIconSize}
                className={cn(
                  'absolute top-1/2 -translate-y-1/2 text-primary animate-spin pointer-events-none',
                  isMobile ? 'left-3' : 'left-2',
                )}
              />
            ) : (
              <Search
                size={fieldIconSize}
                className={cn(
                  'absolute top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none',
                  isMobile ? 'left-3' : 'left-2',
                )}
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
                'w-full rounded-lg border border-border bg-background',
                'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/30',
                isMobile ? 'py-2.5 pl-10 pr-12 text-base' : 'py-1.5 pl-7 pr-8 text-xs',
              )}
            />
            {localKeyword && (
              <button
                onClick={handleClearSearch}
                aria-label={t('chat.historySearch.clear')}
                className={cn(
                  'absolute top-1/2 -translate-y-1/2 flex items-center justify-center rounded-lg hover:bg-black/5 dark:hover:bg-white/5',
                  isMobile ? 'right-0.5 size-10' : 'right-1 size-6',
                )}
              >
                <X size={fieldIconSize} className="text-muted-foreground" />
              </button>
            )}
          </div>
        </div>
      )}
    </>
  );
}
