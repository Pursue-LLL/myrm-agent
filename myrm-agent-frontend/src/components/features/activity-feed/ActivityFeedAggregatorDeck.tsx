'use client';

/**
 * [INPUT]
 * - @/components/features/activity-feed/activityFeedTypes
 * - @/components/features/activity-feed/activityFeedEngine
 * - @/components/features/activity-feed/useActivityFeedStore
 * - @/components/features/activity-feed/ActivityFeedStreamCard
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - ActivityFeedAggregatorDeck (POS: Executive multi-system activity feed aggregator console)
 *
 * [POS]
 * Implementation for Item 190 main deck.
 * Collects heterogeneous events across 6 source systems and orchestrates auto-evaporating queues.
 */

import React, { memo, useMemo, useState, useCallback } from 'react';
import {
  Inbox,
  Search,
  Pause,
  Play,
  Archive,
  RotateCcw,
  Trash2,
  X,
  Layers,
} from 'lucide-react';
import type { FeedSourceSystem } from './activityFeedTypes';
import { sortActivityFeed, filterActivityFeed } from './activityFeedEngine';
import { useActivityFeedStore } from './useActivityFeedStore';
import { ActivityFeedStreamCard } from './ActivityFeedStreamCard';

interface ActivityFeedAggregatorDeckProps {
  readonly className?: string;
}

const SOURCE_TABS: readonly { key: FeedSourceSystem | 'all'; label: string }[] = [
  { key: 'all', label: '全源汇总' },
  { key: 'approval', label: '审批' },
  { key: 'email', label: '邮件' },
  { key: 'calendar', label: '日程' },
  { key: 'messaging', label: '消息' },
  { key: 'cron', label: '定时' },
  { key: 'kanban', label: '看板' },
];

export const ActivityFeedAggregatorDeck = memo(function ActivityFeedAggregatorDeck({
  className = '',
}: ActivityFeedAggregatorDeckProps) {
  const items = useActivityFeedStore((s) => s.items);
  const archive = useActivityFeedStore((s) => s.archive);
  const filter = useActivityFeedStore((s) => s.filter);
  const isPaused = useActivityFeedStore((s) => s.isEvaporationPaused);
  const setFilter = useActivityFeedStore((s) => s.setFilter);
  const togglePause = useActivityFeedStore((s) => s.togglePauseEvaporation);
  const undoEvaporation = useActivityFeedStore((s) => s.undoEvaporation);
  const clearArchive = useActivityFeedStore((s) => s.clearArchive);

  const [archiveDrawerOpen, setArchiveDrawerOpen] = useState(false);

  const processedItems = useMemo(() => {
    const sorted = sortActivityFeed(items);
    return filterActivityFeed(sorted, filter);
  }, [items, filter]);

  const toggleDrawer = useCallback(() => {
    setArchiveDrawerOpen((prev) => !prev);
  }, []);

  return (
    <section
      aria-label="多系统事项聚合活动流"
      className={`flex flex-col w-full rounded-2xl border border-neutral-800 bg-neutral-950 p-4 shadow-xl text-neutral-100 ${className}`}
    >
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-neutral-800/80">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <Layers className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-neutral-100">事项聚合活动流</h2>
            <p className="text-xs text-neutral-400">
              六源事项集中调度，自治事项处理完成自动蒸发消除
            </p>
          </div>
        </div>

        {/* Global Controls: Pause Evaporation & Archive Drawer Trigger */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => togglePause()}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
              isPaused
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20'
                : 'bg-neutral-900 border-neutral-800 text-neutral-300 hover:bg-neutral-800'
            }`}
          >
            {isPaused ? (
              <>
                <Play className="w-3.5 h-3.5" aria-hidden="true" />
                <span>恢复自动蒸发</span>
              </>
            ) : (
              <>
                <Pause className="w-3.5 h-3.5" aria-hidden="true" />
                <span>暂停蒸发</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={toggleDrawer}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-neutral-800 bg-neutral-900 text-neutral-300 hover:bg-neutral-800 text-xs font-medium transition-colors"
            aria-label={`已蒸发备查归档：${archive.length}项`}
          >
            <Archive className="w-3.5 h-3.5 text-neutral-400" aria-hidden="true" />
            <span>已蒸发备查</span>
            {archive.length > 0 ? (
              <span className="px-1.5 py-0.2 rounded-full bg-neutral-800 text-[10px] text-neutral-400">
                {archive.length}
              </span>
            ) : null}
          </button>
        </div>
      </div>

      {/* Filter and Tab Strip */}
      <div className="mt-3.5 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1 overflow-x-auto text-xs scrollbar-none">
            {SOURCE_TABS.map((tab) => {
              const isActive = filter.sourceSystem === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setFilter({ sourceSystem: tab.key })}
                  className={`px-3 py-1 rounded-full whitespace-nowrap transition-colors ${
                    isActive
                      ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30 font-medium'
                      : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          <label className="flex items-center gap-1.5 text-xs text-neutral-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={filter.onlyHumanRequired}
              onChange={(e) => setFilter({ onlyHumanRequired: e.target.checked })}
              className="rounded bg-neutral-900 border-neutral-700 text-sky-500 focus:ring-0 w-3.5 h-3.5"
            />
            <span>只看待你拍板</span>
          </label>
        </div>

        {/* Search input */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
          <input
            type="text"
            value={filter.searchQuery}
            onChange={(e) => setFilter({ searchQuery: e.target.value })}
            placeholder="搜索六源事件标题、描述或编号..."
            className="w-full bg-neutral-900/80 border border-neutral-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-neutral-200 placeholder:text-neutral-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            aria-label="搜索活动流事件"
          />
        </div>
      </div>

      {/* Main Stream Deck */}
      <div className="mt-4 space-y-2.5 min-h-[160px]">
        {processedItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-10 text-neutral-500 text-xs">
            <Inbox className="w-8 h-8 opacity-40 mb-2" aria-hidden="true" />
            <span>暂无聚合事项，多系统自治平稳运行</span>
          </div>
        ) : (
          processedItems.map((item) => (
            <ActivityFeedStreamCard key={item.id} item={item} />
          ))
        )}
      </div>

      {/* Evaporated Archive Drawer/Modal */}
      {archiveDrawerOpen ? (
        <dialog
          open
          aria-labelledby="archive-drawer-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm m-0 max-w-none max-h-none w-full h-full border-0"
        >
          <div className="w-full max-w-md rounded-xl border border-neutral-700/80 bg-neutral-900 p-5 shadow-2xl text-neutral-100 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-neutral-800">
              <div className="flex items-center gap-2">
                <Archive className="w-4 h-4 text-sky-400" aria-hidden="true" />
                <h3 id="archive-drawer-title" className="text-sm font-semibold">
                  已自动蒸发归档备查 ({archive.length})
                </h3>
              </div>
              <button
                type="button"
                onClick={toggleDrawer}
                className="p-1 rounded text-neutral-400 hover:text-neutral-200"
                aria-label="关闭归档备查"
              >
                <X className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>

            <div className="mt-3 max-h-72 overflow-y-auto divide-y divide-neutral-800/80 space-y-1">
              {archive.length === 0 ? (
                <div className="p-8 text-center text-xs text-neutral-500">
                  暂无已蒸发归档条目
                </div>
              ) : (
                archive.map((archived) => (
                  <div key={archived.id} className="p-2.5 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium text-xs truncate">{archived.title}</div>
                      <div className="text-[11px] text-neutral-400 truncate">{archived.summary}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => undoEvaporation(archived.id)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-sky-400 text-xs shrink-0 transition-colors"
                      title="撤销蒸发恢复至活动流"
                    >
                      <RotateCcw className="w-3 h-3" aria-hidden="true" />
                      <span>撤销蒸发</span>
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-neutral-800 flex justify-between items-center">
              <button
                type="button"
                onClick={clearArchive}
                disabled={archive.length === 0}
                className="flex items-center gap-1 text-xs text-neutral-400 hover:text-rose-400 disabled:opacity-40 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                <span>清空归档</span>
              </button>
              <button
                type="button"
                onClick={toggleDrawer}
                className="px-3 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </dialog>
      ) : null}
    </section>
  );
});
