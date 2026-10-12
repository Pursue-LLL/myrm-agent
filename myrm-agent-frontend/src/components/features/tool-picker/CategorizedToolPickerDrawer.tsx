/**
 * [INPUT]
 * @/hooks/ui/useCategorizedToolPicker::useCategorizedToolPicker, CategorizedToolItem, ToolCategory
 * @/components/features/tool-picker/ToolCategoryTabs::ToolCategoryTabs
 * @/components/features/tool-picker/ToolPickerCard::ToolPickerCard
 * @/components/features/icons/PremiumIcons (IconSearch, IconX, IconWrench, IconCheck)
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - CategorizedToolPickerDrawer: Semantic dialog drawer for categorized tools, pinning, and instant filter
 *
 * [POS]
 * Modal drawer component for CategorizedToolPickerWithPinningAndInstantFilter (Item 15).
 * Single file < 280 lines. Zero `any` types.
 */

'use client';

import React, { useEffect, useRef, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import type { CategorizedToolItem, ToolCategory } from '@/hooks/ui/useCategorizedToolPicker';
import { useCategorizedToolPicker } from '@/hooks/ui/useCategorizedToolPicker';
import { ToolCategoryTabs } from './ToolCategoryTabs';
import { ToolPickerCard } from './ToolPickerCard';
import { IconSearch, IconX, IconWrench } from '@/components/features/icons/PremiumIcons';

export interface CategorizedToolPickerDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectTool?: (tool: CategorizedToolItem) => void;
}

export const CategorizedToolPickerDrawer: React.FC<CategorizedToolPickerDrawerProps> = ({
  isOpen,
  onClose,
  onSelectTool,
}) => {
  const t = useTranslations('toolPicker');
  const dialogRef = useRef<HTMLDialogElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const {
    tools,
    activeCategory,
    setActiveCategory,
    searchQuery,
    setSearchQuery,
    pinnedIds,
    togglePin,
    recentTools,
    recordRecent,
    toggleToolEnabled,
    filteredTools,
    pinnedTools,
  } = useCategorizedToolPicker();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (isOpen) {
      if (!dialog.open) {
        dialog.showModal();
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
    } else {
      if (dialog.open) {
        dialog.close();
      }
    }
  }, [isOpen]);

  const categoryCounts = useMemo(() => {
    const counts: Record<ToolCategory, number> = {
      all: tools.length,
      system: tools.filter((t) => t.category === 'system').length,
      browser: tools.filter((t) => t.category === 'browser').length,
      code: tools.filter((t) => t.category === 'code').length,
      docs: tools.filter((t) => t.category === 'docs').length,
    };
    return counts;
  }, [tools]);

  const handleSelectTool = useCallback(
    (tool: CategorizedToolItem) => {
      recordRecent(tool.id);
      onSelectTool?.(tool);
    },
    [recordRecent, onSelectTool],
  );

  if (!isOpen) {
    return null;
  }

  return (
    <dialog
      ref={dialogRef}
      onCancel={onClose}
      className="fixed inset-0 m-auto z-50 flex flex-col h-[85vh] w-[90vw] max-w-4xl rounded-3xl border border-zinc-200/90 bg-white dark:border-zinc-800 dark:bg-zinc-950 p-0 shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm overflow-hidden"
    >
      {/* Header Bar */}
      <div className="flex items-center justify-between border-b border-zinc-100 dark:border-zinc-800/80 px-6 py-4 bg-zinc-50/60 dark:bg-zinc-900/40">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 shadow-sm">
            <IconWrench className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {t('modalTitle')}
            </h2>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {t('modalSubtitle')}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label={t('closeAriaLabel')}
          className="p-1.5 rounded-xl text-zinc-400 hover:text-zinc-700 hover:bg-zinc-200/60 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 transition-colors"
        >
          <IconX className="w-4 h-4" />
        </button>
      </div>

      {/* Filter and Category Strip */}
      <div className="px-6 pt-4 pb-2 border-b border-zinc-100 dark:border-zinc-800/60 space-y-3 bg-white dark:bg-zinc-950">
        {/* Instant Search Bar */}
        <div className="relative flex items-center">
          <IconSearch className="absolute left-3.5 w-4 h-4 text-zinc-400" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="w-full pl-10 pr-9 py-2 rounded-xl border border-zinc-200 bg-zinc-50/70 text-xs text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-100 dark:focus:ring-zinc-100/10 dark:focus:border-zinc-600 transition-all"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              aria-label={t('clearSearch')}
              className="absolute right-3 p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            >
              <IconX className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Category Tabs */}
        <ToolCategoryTabs
          activeCategory={activeCategory}
          onSelectCategory={setActiveCategory}
          categoryCounts={categoryCounts}
        />
      </div>

      {/* Scrollable Tool Items Container */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Pinned Section (if any & no search query) */}
        {!searchQuery && activeCategory === 'all' && pinnedTools.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <h3 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                {t('pinnedSection')}
              </h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {pinnedTools.map((tool) => (
                <ToolPickerCard
                  key={`pinned-${tool.id}`}
                  tool={tool}
                  isPinned={true}
                  onTogglePin={togglePin}
                  onToggleEnabled={toggleToolEnabled}
                  onSelect={handleSelectTool}
                />
              ))}
            </div>
          </div>
        )}

        {/* Recently Used Section (if any & no search query) */}
        {!searchQuery && activeCategory === 'all' && recentTools.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              <h3 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                {t('recentSection')}
              </h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {recentTools.map((tool) => (
                <ToolPickerCard
                  key={`recent-${tool.id}`}
                  tool={tool}
                  isPinned={pinnedIds.includes(tool.id)}
                  onTogglePin={togglePin}
                  onToggleEnabled={toggleToolEnabled}
                  onSelect={handleSelectTool}
                />
              ))}
            </div>
          </div>
        )}

        {/* Filtered Tool Grid */}
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <h3 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
              {searchQuery ? t('allToolsSection') : t('allToolsSection')}
            </h3>
            <span className="text-[11px] text-zinc-400">
              {t('toolsCount', { count: filteredTools.length })}
            </span>
          </div>

          {filteredTools.length === 0 ? (
            <div className="py-12 text-center text-zinc-400 dark:text-zinc-500">
              <p className="text-xs font-medium">{t('noToolsFound')}</p>
              <p className="mt-1 text-[11px] text-zinc-400/80">
                {t('noToolsFoundHint')}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {filteredTools.map((tool) => (
                <ToolPickerCard
                  key={tool.id}
                  tool={tool}
                  isPinned={pinnedIds.includes(tool.id)}
                  onTogglePin={togglePin}
                  onToggleEnabled={toggleToolEnabled}
                  onSelect={handleSelectTool}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </dialog>
  );
};
