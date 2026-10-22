/**
 * [INPUT]
 * - widgetDashboardTypes: PinnedDashboardDrawerProps, PinnedWidget, WidgetNetworkPolicy
 * - usePinnedDashboardStore: usePinnedDashboardStore
 *
 * [OUTPUT]
 * - PinnedDashboardDrawer: Slide-out drawer for session-pinned interactive widgets and dashboard management
 *
 * [POS]
 * Slide-out drawer component for pinned interactive widgets (Item 48 P0).
 * Strictly under 320 lines. Zero `any`.
 */

'use client';

import React, { memo, useCallback } from 'react';
import {
  Pin,
  PinOff,
  Image as ImageIcon,
  Shield,
  Trash2,
  X,
  Sparkles,
  Layers,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { usePinnedDashboardStore } from './usePinnedDashboardStore';
import type { PinnedDashboardDrawerProps, WidgetNetworkPolicy } from './widgetDashboardTypes';

export const PinnedDashboardDrawer: React.FC<PinnedDashboardDrawerProps> = memo(({
  chatId,
  isOpen,
  onClose,
  className = '',
  onExportPoster,
}) => {
  const t = useTranslations('widgetDashboard');

  const {
    pinnedWidgets,
    unpinWidget,
    setNetworkPolicy,
    clearAllPins,
    setActiveExportWidget,
  } = usePinnedDashboardStore();

  const filteredWidgets = chatId
    ? pinnedWidgets.filter((w) => !w.chatId || w.chatId === chatId)
    : pinnedWidgets;

  const handleTriggerExport = useCallback((widget: typeof pinnedWidgets[0]) => {
    setActiveExportWidget(widget);
    if (onExportPoster) {
      onExportPoster(widget);
    }
  }, [setActiveExportWidget, onExportPoster]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      data-testid="pinned-dashboard-drawer-root"
      className={`fixed inset-0 z-50 flex justify-end transition-all ${className}`}
    >
      {/* Backdrop */}
      <button
        type="button"
        className="fixed inset-0 bg-black/30 backdrop-blur-2xs cursor-default"
        onClick={onClose}
        aria-label={t('drawerTitle')}
      />
      <aside
        data-testid="pinned-dashboard-drawer"
        aria-label={t('drawerTitle')}
        className="w-[420px] max-w-[90vw] h-full bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-200"
      >
        {/* Header */}
        <header className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400">
              <Layers className="w-4 h-4" />
            </span>
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                <span>{t('drawerTitle')}</span>
                <span
                  data-testid="pinned-count-badge"
                  className="px-1.5 py-0.2 text-[10px] font-bold rounded-full bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300"
                >
                  {filteredWidgets.length}
                </span>
              </h3>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                {t('drawerSubtitle')}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {filteredWidgets.length > 0 && (
              <button
                type="button"
                data-testid="clear-all-pins-btn"
                onClick={clearAllPins}
                title={t('clearAll')}
                className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
            <button
              type="button"
              data-testid="close-drawer-btn"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Content List */}
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3.5">
          {filteredWidgets.length === 0 ? (
            <div
              data-testid="empty-pinned-view"
              className="h-full flex flex-col items-center justify-center p-8 text-center text-slate-400"
            >
              <Pin className="w-10 h-10 mb-3 stroke-[1.5] text-slate-300 dark:text-slate-600" />
              <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {t('emptyTitle')}
              </h4>
              <p className="text-[11px] mt-1 max-w-[220px] text-slate-400">
                {t('emptyDescription')}
              </p>
            </div>
          ) : (
            filteredWidgets.map((widget) => (
              <div
                key={widget.id}
                data-testid={`pinned-widget-card-${widget.artifactId}`}
                className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 shadow-xs flex flex-col gap-2.5 transition-all"
              >
                {/* Card Title & Type */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 uppercase">
                        {widget.type}
                      </span>
                      <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate">
                        {widget.title}
                      </h4>
                    </div>
                    <span className="text-[10px] text-slate-400 mt-0.5 block">
                      {new Date(widget.pinnedAt).toLocaleTimeString()}
                    </span>
                  </div>

                  {/* Unpin Action */}
                  <button
                    type="button"
                    data-testid={`unpin-btn-${widget.artifactId}`}
                    onClick={() => {
                      unpinWidget(widget.artifactId);
                    }}
                    title={t('unpin')}
                    className="p-1 text-slate-400 hover:text-amber-500 rounded transition-colors"
                  >
                    <PinOff className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Content Snapshot Preview Snippet */}
                <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800/80 text-[11px] font-mono text-slate-600 dark:text-slate-300 max-h-24 overflow-hidden select-text">
                  {widget.content.slice(0, 200)}...
                </div>

                {/* Card Footer: Network Policy Selector & Poster Export */}
                <div className="flex items-center justify-between gap-2 pt-1 border-t border-slate-100 dark:border-slate-700/60 text-xs">
                  {/* Network Policy */}
                  <div className="flex items-center gap-1.5">
                    <Shield className="w-3 h-3 text-slate-400" />
                    <select
                      data-testid={`policy-select-${widget.artifactId}`}
                      value={widget.networkPolicy}
                      onChange={(e) => {
                        setNetworkPolicy(widget.artifactId, e.target.value as WidgetNetworkPolicy);
                      }}
                      className="bg-transparent text-[11px] text-slate-600 dark:text-slate-300 focus:outline-none cursor-pointer"
                    >
                      <option value="none" className="dark:bg-slate-800">
                        {t('policyNone')}
                      </option>
                      <option value="restricted" className="dark:bg-slate-800">
                        {t('policyRestricted')}
                      </option>
                      <option value="full" className="dark:bg-slate-800">
                        {t('policyFull')}
                      </option>
                    </select>
                  </div>

                  {/* Export Poster Button */}
                  <button
                    type="button"
                    data-testid={`export-poster-btn-${widget.artifactId}`}
                    onClick={() => {
                      handleTriggerExport(widget);
                    }}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/60 rounded-md transition-colors"
                  >
                    <ImageIcon className="w-3 h-3" />
                    <span>{t('exportPoster')}</span>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
});

PinnedDashboardDrawer.displayName = 'PinnedDashboardDrawer';
