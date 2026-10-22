/**
 * [INPUT] PinnedDashboardWidget list, layout state, active filters
 * [OUTPUT] DashboardWorkspaceDrawer (Full-featured responsive dashboard canvas)
 * [POS] Features -> Dashboard Workspace -> DashboardWorkspaceDrawer
 */

'use client';

import React, { useMemo, useState, useCallback } from 'react';
import {
  LayoutDashboard,
  Search,
  RefreshCw,
  X,
  Trash2,
  Maximize2,
  Minimize2,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useDashboardWorkspaceStore } from './useDashboardWorkspaceStore';
import { DashboardWidgetCard } from './DashboardWidgetCard';

export interface DashboardWorkspaceDrawerProps {
  className?: string;
}

export const DashboardWorkspaceDrawer: React.FC<DashboardWorkspaceDrawerProps> = ({
  className,
}) => {
  const {
    widgets,
    isDrawerOpen,
    searchQuery,
    activeTagFilter,
    closeDrawer,
    unpinWidget,
    updateWidgetColSpan,
    updateWidgetTitle,
    updateWidgetRefreshInterval,
    refreshWidget,
    setSearchQuery,
    setActiveTagFilter,
    clearAllWidgets,
  } = useDashboardWorkspaceStore();

  const [isFullScreen, setIsFullScreen] = useState(false);

  const allTags = useMemo(() => {
    const tagSet = new Set<string>();
    for (const widget of widgets) {
      for (const tag of widget.tags) {
        tagSet.add(tag);
      }
    }
    return Array.from(tagSet);
  }, [widgets]);

  const filteredWidgets = useMemo(() => {
    return widgets.filter((widget) => {
      const matchesSearch =
        searchQuery.trim() === '' ||
        widget.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        widget.content.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesTag =
        activeTagFilter === null || widget.tags.includes(activeTagFilter);

      return matchesSearch && matchesTag;
    });
  }, [widgets, searchQuery, activeTagFilter]);

  const handleRefreshAll = useCallback(() => {
    for (const widget of widgets) {
      refreshWidget(widget.id);
    }
  }, [widgets, refreshWidget]);

  if (!isDrawerOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      aria-label="数字员工监控工作台"
      className={cn(
        'fixed inset-y-0 right-0 z-50 m-0 p-0 border-0 border-l border-neutral-200 dark:border-neutral-800 max-w-none max-h-none h-full flex flex-col bg-neutral-50 dark:bg-neutral-900 shadow-2xl transition-all duration-200 ease-out',
        isFullScreen ? 'inset-x-0 w-full' : 'w-full md:w-[85vw] lg:w-[75vw] xl:w-[65vw]',
        className,
      )}
    >
      {/* Header Bar */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <LayoutDashboard size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
                项目工作台与监控大盘
              </h2>
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300">
                {widgets.length} 个组件
              </span>
            </div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              常驻持久化富交互原型、动态数据报表与数字员工监控卡片
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {widgets.length > 0 ? (
            <>
              <button
                type="button"
                onClick={handleRefreshAll}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 transition-colors"
                title="刷新所有组件"
              >
                <RefreshCw size={13} />
                <span>全部刷新</span>
              </button>
              <button
                type="button"
                onClick={clearAllWidgets}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 border border-red-200 dark:border-red-900/50 transition-colors"
                title="清空所有组件"
              >
                <Trash2 size={13} />
                <span>清空</span>
              </button>
            </>
          ) : null}

          <button
            type="button"
            onClick={() => setIsFullScreen(!isFullScreen)}
            className="p-2 rounded-lg text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            title={isFullScreen ? '还原视口' : '全屏展示'}
            aria-label={isFullScreen ? '还原视口' : '全屏展示'}
          >
            {isFullScreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>

          <button
            type="button"
            onClick={closeDrawer}
            className="p-2 rounded-lg text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            title="关闭工作台"
            aria-label="关闭工作台"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      {widgets.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3 border-b border-neutral-200 dark:border-neutral-800 bg-neutral-100/60 dark:bg-neutral-900/40">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索组件标题或内容..."
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto">
            <button
              type="button"
              onClick={() => setActiveTagFilter(null)}
              className={cn(
                'px-2.5 py-1 text-xs font-medium rounded-full transition-colors',
                activeTagFilter === null
                  ? 'bg-amber-600 text-white'
                  : 'bg-neutral-200 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-300 dark:hover:bg-neutral-700',
              )}
            >
              全部
            </button>
            {allTags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setActiveTagFilter(tag)}
                className={cn(
                  'px-2.5 py-1 text-xs font-medium rounded-full transition-colors uppercase font-mono',
                  activeTagFilter === tag
                    ? 'bg-amber-600 text-white'
                    : 'bg-neutral-200 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-300 dark:hover:bg-neutral-700',
                )}
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-6">
        {filteredWidgets.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full min-h-[360px] text-center p-8 border-2 border-dashed border-neutral-300 dark:border-neutral-800 rounded-2xl bg-white/50 dark:bg-neutral-900/30">
            <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-amber-500/10 text-amber-500 mb-4">
              <Sparkles size={28} />
            </div>
            <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
              工作台尚无固定组件
            </h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 max-w-sm mb-4">
              在对话消息中 Agent 生成的任意 HTML / SVG / 数据看板卡片右上角，点击固定图标，即可将其钉入此专属工作台，告别单次问答刷屏遗忘。
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredWidgets.map((widget) => (
              <DashboardWidgetCard
                key={widget.id}
                widget={widget}
                onUpdateColSpan={updateWidgetColSpan}
                onUpdateTitle={updateWidgetTitle}
                onUpdateRefreshInterval={updateWidgetRefreshInterval}
                onRefresh={refreshWidget}
                onUnpin={unpinWidget}
              />
            ))}
          </div>
        )}
      </div>
    </dialog>
  );
};

DashboardWorkspaceDrawer.displayName = 'DashboardWorkspaceDrawer';
