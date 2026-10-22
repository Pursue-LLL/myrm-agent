/**
 * [INPUT] PinnedDashboardWidget, update actions (colSpan, title, interval, refresh, unpin)
 * [OUTPUT] DashboardWidgetCard (Individual responsive card with sandbox preview and toolbar)
 * [POS] Features -> Dashboard Workspace -> DashboardWidgetCard
 */

'use client';

import React, { useState, useCallback } from 'react';
import {
  RefreshCw,
  Trash2,
  Columns2,
  Columns3,
  Clock,
  Check,
  Edit2,
  Square,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { HtmlPreview } from '@/components/features/artifacts/renderers/MediaPreview';
import type {
  AutoRefreshIntervalSeconds,
  PinnedDashboardWidget,
  WidgetColSpan,
} from './dashboardWorkspaceTypes';

export interface DashboardWidgetCardProps {
  widget: PinnedDashboardWidget;
  onUpdateColSpan: (id: string, colSpan: WidgetColSpan) => void;
  onUpdateTitle: (id: string, title: string) => void;
  onUpdateRefreshInterval: (id: string, interval: AutoRefreshIntervalSeconds) => void;
  onRefresh: (id: string) => void;
  onUnpin: (id: string) => void;
  className?: string;
}

export const DashboardWidgetCard: React.FC<DashboardWidgetCardProps> = ({
  widget,
  onUpdateColSpan,
  onUpdateTitle,
  onUpdateRefreshInterval,
  onRefresh,
  onUnpin,
  className,
}) => {
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [tempTitle, setTempTitle] = useState(widget.title);

  const handleStartEdit = useCallback(() => {
    setTempTitle(widget.title);
    setIsEditingTitle(true);
  }, [widget.title]);

  const handleSaveTitle = useCallback(() => {
    if (tempTitle.trim()) {
      onUpdateTitle(widget.id, tempTitle.trim());
    }
    setIsEditingTitle(false);
  }, [tempTitle, widget.id, onUpdateTitle]);

  const colSpanClass =
    widget.colSpan === '3'
      ? 'col-span-full'
      : widget.colSpan === '2'
      ? 'md:col-span-2'
      : 'col-span-1';

  return (
    <div
      className={cn(
        'flex flex-col bg-white dark:bg-neutral-800/90 border border-neutral-200 dark:border-neutral-700/80 rounded-xl shadow-sm overflow-hidden transition-shadow hover:shadow-md',
        colSpanClass,
        className,
      )}
    >
      {/* Card Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-neutral-200 dark:border-neutral-700 bg-neutral-50/70 dark:bg-neutral-850/50">
        <div className="flex items-center gap-2 flex-1 min-w-0 mr-2">
          {isEditingTitle ? (
            <div className="flex items-center gap-1 flex-1">
              <input
                type="text"
                value={tempTitle}
                onChange={(e) => setTempTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleSaveTitle();
                  }
                }}
                className="w-full px-2 py-0.5 text-xs bg-white dark:bg-neutral-900 border border-amber-500 rounded text-neutral-900 dark:text-neutral-100 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleSaveTitle}
                className="p-1 rounded text-green-600 hover:bg-green-50 dark:hover:bg-green-950/40"
              >
                <Check size={13} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 truncate">
              <button
                type="button"
                className="text-left text-xs font-semibold text-neutral-800 dark:text-neutral-200 truncate hover:underline"
                onClick={handleStartEdit}
                title="点击重命名"
              >
                {widget.title}
              </button>
              <button
                type="button"
                onClick={handleStartEdit}
                className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                title="编辑标题"
              >
                <Edit2 size={11} />
              </button>
              <span className="px-1.5 py-0.2 text-[10px] font-mono uppercase rounded bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
                {widget.language}
              </span>
            </div>
          )}
        </div>

        {/* Toolbar Actions */}
        <div className="flex items-center gap-1 shrink-0">
          {/* ColSpan Switcher */}
          <button
            type="button"
            onClick={() =>
              onUpdateColSpan(
                widget.id,
                widget.colSpan === '1'
                  ? '2'
                  : widget.colSpan === '2'
                  ? '3'
                  : '1',
              )
            }
            className="p-1 rounded text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
            title={`切换布局宽档 (当前 ${widget.colSpan} 列)`}
          >
            {widget.colSpan === '1' ? (
              <Square size={13} />
            ) : widget.colSpan === '2' ? (
              <Columns2 size={13} />
            ) : (
              <Columns3 size={13} />
            )}
          </button>

          {/* Refresh Interval Selector */}
          <select
            aria-label="自动刷新频率"
            value={widget.autoRefreshInterval}
            onChange={(e) =>
              onUpdateRefreshInterval(
                widget.id,
                Number(e.target.value) as AutoRefreshIntervalSeconds,
              )
            }
            className="text-[10px] px-1 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 border-none rounded cursor-pointer focus:outline-none"
          >
            <option value={0}>手动</option>
            <option value={15}>15s</option>
            <option value={30}>30s</option>
            <option value={60}>1m</option>
            <option value={300}>5m</option>
          </select>

          {/* Manual Refresh */}
          <button
            type="button"
            onClick={() => onRefresh(widget.id)}
            className="p-1 rounded text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
            title="立即刷新"
          >
            <RefreshCw size={13} />
          </button>

          {/* Unpin */}
          <button
            type="button"
            onClick={() => onUnpin(widget.id)}
            className="p-1 rounded text-neutral-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
            title="取消固定"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Card Body — Sandboxed Widget */}
      <div className="p-3 bg-neutral-50/30 dark:bg-neutral-900/50 flex-1 min-h-[160px] max-h-[450px] overflow-auto">
        <HtmlPreview content={widget.content} injectTheme autoHeight />
      </div>

      {/* Card Footer */}
      <div className="flex items-center justify-between px-3 py-1.5 text-[10px] text-neutral-400 dark:text-neutral-500 border-t border-neutral-100 dark:border-neutral-800 bg-white dark:bg-neutral-850">
        <div className="flex items-center gap-1">
          <Clock size={10} />
          <span>
            固定于 {new Date(widget.pinnedAt).toLocaleTimeString()}
          </span>
        </div>
        <span>
          已刷新 {new Date(widget.lastRefreshedAt).toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
};

DashboardWidgetCard.displayName = 'DashboardWidgetCard';
