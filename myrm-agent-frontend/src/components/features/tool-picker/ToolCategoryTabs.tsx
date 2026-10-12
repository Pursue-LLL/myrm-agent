/**
 * [INPUT]
 * @/hooks/ui/useCategorizedToolPicker::ToolCategory
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - ToolCategoryTabs: Category tab strip with item count badges
 *
 * [POS]
 * Sub-component for CategorizedToolPickerWithPinningAndInstantFilter (Item 15).
 * Single file < 120 lines. Zero `any` types.
 */

'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import type { ToolCategory } from '@/hooks/ui/useCategorizedToolPicker';

export interface ToolCategoryTabsProps {
  activeCategory: ToolCategory;
  onSelectCategory: (cat: ToolCategory) => void;
  categoryCounts: Record<ToolCategory, number>;
}

const CATEGORY_KEYS: { id: ToolCategory; labelKey: string }[] = [
  { id: 'all', labelKey: 'tabAll' },
  { id: 'system', labelKey: 'tabSystem' },
  { id: 'browser', labelKey: 'tabBrowser' },
  { id: 'code', labelKey: 'tabCode' },
  { id: 'docs', labelKey: 'tabDocs' },
];

export const ToolCategoryTabs: React.FC<ToolCategoryTabsProps> = ({
  activeCategory,
  onSelectCategory,
  categoryCounts,
}) => {
  const t = useTranslations('toolPicker');

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
      {CATEGORY_KEYS.map(({ id, labelKey }) => {
        const isActive = activeCategory === id;
        const count = categoryCounts[id] || 0;

        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelectCategory(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium whitespace-nowrap transition-all ${
              isActive
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 shadow-sm'
                : 'bg-zinc-100/80 text-zinc-600 hover:bg-zinc-200/70 hover:text-zinc-900 dark:bg-zinc-800/60 dark:text-zinc-400 dark:hover:bg-zinc-700/60 dark:hover:text-zinc-200'
            }`}
          >
            <span>{t(labelKey)}</span>
            <span
              className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                isActive
                  ? 'bg-zinc-700 text-zinc-200 dark:bg-zinc-300 dark:text-zinc-800'
                  : 'bg-zinc-200/80 text-zinc-500 dark:bg-zinc-700/70 dark:text-zinc-400'
              }`}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
};
