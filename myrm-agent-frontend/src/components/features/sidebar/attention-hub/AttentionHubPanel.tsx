'use client';

/**
 * [INPUT]
 * - @/components/features/sidebar/attention-hub/useAttentionHubStore
 * - @/components/features/sidebar/attention-hub/attentionHubEngine
 * - @/components/features/sidebar/attention-hub/attentionHubTypes
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - AttentionHubPanel (POS: Expandable attention drawer/panel with direct focus shuttle)
 *
 * [POS]
 * Implementation for Item 189 attention hub drawer.
 * Displays blocking tasks across concurrent sessions and provides one-click focus shuttle navigation.
 */

import React, { memo, useMemo, useCallback } from 'react';
import {
  X,
  Search,
  CheckCheck,
  Trash2,
  Clock,
  ExternalLink,
  ShieldAlert,
  HelpCircle,
  AlertTriangle,
  CheckCircle2,
  Inbox,
} from 'lucide-react';
import { useAttentionHubStore } from './useAttentionHubStore';
import {
  sortAttentionItems,
  filterAttentionItems,
  getCategoryMeta,
  formatRemainingTime,
} from './attentionHubEngine';
import type { AttentionCategory, AttentionItem } from './attentionHubTypes';

interface AttentionHubPanelProps {
  readonly className?: string;
  readonly onNavigateToChat?: (chatId: string) => void;
}

const CATEGORY_TABS: readonly { key: AttentionCategory | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'approval_blocking', label: '待审批' },
  { key: 'clarification_needed', label: '待答复' },
  { key: 'task_failed', label: '异常' },
  { key: 'task_completed', label: '已完成' },
];

export const AttentionHubPanel = memo(function AttentionHubPanel({
  className = '',
  onNavigateToChat,
}: AttentionHubPanelProps) {
  const isPanelOpen = useAttentionHubStore((s) => s.isPanelOpen);
  const items = useAttentionHubStore((s) => s.items);
  const filter = useAttentionHubStore((s) => s.filter);
  const togglePanel = useAttentionHubStore((s) => s.togglePanel);
  const markAllAsRead = useAttentionHubStore((s) => s.markAllAsRead);
  const batchClearResolved = useAttentionHubStore((s) => s.batchClearResolved);
  const setCategoryFilter = useAttentionHubStore((s) => s.setCategoryFilter);
  const setSearchQuery = useAttentionHubStore((s) => s.setSearchQuery);
  const setOnlyActionRequired = useAttentionHubStore((s) => s.setOnlyActionRequired);
  const shuttleToTarget = useAttentionHubStore((s) => s.shuttleToTarget);

  const processedItems = useMemo(() => {
    const sorted = sortAttentionItems(items);
    return filterAttentionItems(sorted, filter);
  }, [items, filter]);

  const handleClose = useCallback(() => {
    togglePanel(false);
  }, [togglePanel]);

  const handleShuttle = useCallback(
    (item: AttentionItem) => {
      shuttleToTarget(item.id, onNavigateToChat);
    },
    [shuttleToTarget, onNavigateToChat],
  );

  if (!isPanelOpen) {
    return null;
  }

  const renderCategoryIcon = (category: AttentionCategory) => {
    switch (category) {
      case 'approval_blocking': {
        return <ShieldAlert className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />;
      }
      case 'clarification_needed': {
        return <HelpCircle className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />;
      }
      case 'task_failed': {
        return <AlertTriangle className="w-3.5 h-3.5 text-orange-400" aria-hidden="true" />;
      }
      case 'task_completed': {
        return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />;
      }
    }
  };

  return (
    <section
      aria-label="注意力引导中枢"
      className={`flex flex-col w-full max-w-sm rounded-xl border border-neutral-700/80 bg-neutral-900/95 shadow-2xl backdrop-blur-md text-neutral-100 z-50 overflow-hidden ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold tracking-wide uppercase text-neutral-200">
            注意力引导中枢
          </h2>
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-neutral-800 text-neutral-300">
            {processedItems.length}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={markAllAsRead}
            title="全部标为已读"
            className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors"
            aria-label="全部标为已读"
          >
            <CheckCheck className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={batchClearResolved}
            title="清理已完成事项"
            className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors"
            aria-label="清理已完成事项"
          >
            <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors"
            aria-label="关闭面板"
          >
            <X className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Filter and Search */}
      <div className="p-2.5 border-b border-neutral-800/80 space-y-2">
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
          <input
            type="text"
            value={filter.searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索阻塞任务或会话..."
            className="w-full bg-neutral-800/70 border border-neutral-700/60 rounded-md pl-8 pr-2.5 py-1 text-xs text-neutral-200 placeholder:text-neutral-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
            aria-label="搜索注意力条目"
          />
        </div>

        {/* Category Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto pb-0.5 text-[11px] scrollbar-none">
          {CATEGORY_TABS.map((tab) => {
            const isActive = filter.category === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setCategoryFilter(tab.key)}
                className={`px-2 py-0.5 rounded-full whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800'
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-between text-[11px] text-neutral-400 pt-0.5">
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={filter.onlyActionRequired}
              onChange={(e) => setOnlyActionRequired(e.target.checked)}
              className="rounded bg-neutral-800 border-neutral-700 text-rose-500 focus:ring-0 w-3 h-3"
            />
            <span>仅显示需处理阻塞</span>
          </label>
        </div>
      </div>

      {/* Items Scroll Area */}
      <div className="max-h-80 overflow-y-auto divide-y divide-neutral-800/60 p-1 space-y-1">
        {processedItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-neutral-500 text-xs">
            <Inbox className="w-8 h-8 opacity-40 mb-2" aria-hidden="true" />
            <span>暂无注意力待办，一切运行正常</span>
          </div>
        ) : (
          processedItems.map((item) => {
            const meta = getCategoryMeta(item.category);
            const remaining = formatRemainingTime(item.expiresAt);

            const badgeBg =
              meta.badgeColor === 'rose'
                ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                : meta.badgeColor === 'amber'
                ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                : meta.badgeColor === 'orange'
                ? 'bg-orange-500/15 text-orange-300 border-orange-500/30'
                : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';

            return (
              <div
                key={item.id}
                className={`p-2.5 rounded-lg transition-colors hover:bg-neutral-800/40 relative ${
                  !item.isRead ? 'bg-neutral-800/20' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] border font-medium ${badgeBg}`}
                    >
                      {renderCategoryIcon(item.category)}
                      <span>{meta.label}</span>
                    </span>
                    <span className="text-[11px] text-neutral-400 truncate" title={item.chatTitle}>
                      {item.chatTitle}
                    </span>
                  </div>

                  {remaining ? (
                    <span className="flex items-center gap-1 text-[10px] text-rose-400 font-mono shrink-0">
                      <Clock className="w-3 h-3" aria-hidden="true" />
                      <span>{remaining}</span>
                    </span>
                  ) : null}
                </div>

                <div className="mt-1.5 text-xs font-medium text-neutral-200">
                  {item.title}
                </div>

                <div className="mt-0.5 text-[11px] text-neutral-400 line-clamp-2 leading-relaxed">
                  {item.description}
                </div>

                <div className="mt-2.5 flex items-center justify-between pt-1 border-t border-neutral-800/40 text-[11px]">
                  <span className="text-[10px] text-neutral-500">
                    {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>

                  <button
                    type="button"
                    onClick={() => handleShuttle(item)}
                    className="flex items-center gap-1 px-2 py-0.5 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-200 hover:text-white transition-colors"
                  >
                    <span>定位穿梭</span>
                    <ExternalLink className="w-3 h-3" aria-hidden="true" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
});
