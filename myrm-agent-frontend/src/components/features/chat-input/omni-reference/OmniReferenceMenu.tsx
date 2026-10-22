/**
 * [INPUT]
 * - ./omniReferenceTypes::OmniReferenceItem
 * - ./omniReferenceTypes::ReferenceDimension
 * - ./omniReferenceTypes::DimensionFilter
 * - ./useOmniReferenceStore::useOmniReferenceStore
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - OmniReferenceMenu: Floating autocomplete menu for 5-dimensional @ references
 *
 * [POS]
 * Autocomplete popup for chat input.
 * Strictly adheres to 0-any rule, native <dialog> a11y, < 400 lines limit, and zero native emoji.
 */

'use client';

import React, { useEffect, useCallback, memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  FileCode,
  MessageSquare,
  Layers,
  Bot,
  CheckSquare,
  Loader2,
  Sparkles,
  Search,
} from 'lucide-react';
import type { OmniReferenceItem, DimensionFilter, ReferenceDimension } from './omniReferenceTypes';
import { useOmniReferenceStore } from './useOmniReferenceStore';

interface OmniReferenceMenuProps {
  onSelectItem: (item: OmniReferenceItem) => void;
  className?: string;
}

const DIMENSION_TABS: Array<{ key: DimensionFilter; icon: React.ComponentType<{ className?: string }> }> = [
  { key: 'all', icon: Sparkles },
  { key: 'file', icon: FileCode },
  { key: 'session', icon: MessageSquare },
  { key: 'artifact', icon: Layers },
  { key: 'agent', icon: Bot },
  { key: 'task', icon: CheckSquare },
];

function getDimensionIcon(dim: ReferenceDimension): React.ReactElement {
  switch (dim) {
    case 'file':
      return <FileCode className="h-4 w-4 text-sky-500 shrink-0" />;
    case 'session':
      return <MessageSquare className="h-4 w-4 text-emerald-500 shrink-0" />;
    case 'artifact':
      return <Layers className="h-4 w-4 text-indigo-500 shrink-0" />;
    case 'agent':
      return <Bot className="h-4 w-4 text-amber-500 shrink-0" />;
    case 'task':
      return <CheckSquare className="h-4 w-4 text-rose-500 shrink-0" />;
  }
}

export const OmniReferenceMenu = memo<OmniReferenceMenuProps>(({ onSelectItem, className }) => {
  const t = useTranslations('omniReference');

  const isOpen = useOmniReferenceStore((s) => s.isOpen);
  const items = useOmniReferenceStore((s) => s.items);
  const selectedIndex = useOmniReferenceStore((s) => s.selectedIndex);
  const selectedDimension = useOmniReferenceStore((s) => s.selectedDimension);
  const isLoading = useOmniReferenceStore((s) => s.isLoading);
  const closeMenu = useOmniReferenceStore((s) => s.closeMenu);
  const setSelectedDimension = useOmniReferenceStore((s) => s.setSelectedDimension);
  const setSelectedIndex = useOmniReferenceStore((s) => s.setSelectedIndex);
  const selectNext = useOmniReferenceStore((s) => s.selectNext);
  const selectPrev = useOmniReferenceStore((s) => s.selectPrev);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen) {
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectNext();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectPrev();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (items[selectedIndex]) {
          onSelectItem(items[selectedIndex]);
          closeMenu();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeMenu();
      }
    },
    [isOpen, items, selectedIndex, onSelectItem, closeMenu, selectNext, selectPrev]
  );

  useEffect(() => {
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  if (!isOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="omni-reference-title"
      data-testid="omni-reference-menu"
      className={`fixed bottom-24 z-50 w-full max-w-md rounded-xl border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 p-0 overflow-hidden ${
        className || ''
      }`}
    >
      {/* Header and Dimension Filter Tabs */}
      <div className="border-b border-zinc-100 bg-zinc-50/80 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-800/40">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-700 dark:text-zinc-300">
            <Search className="h-3.5 w-3.5 text-amber-500" />
            <span id="omni-reference-title">{t('title')}</span>
          </div>
          <span className="text-[10px] text-zinc-400 font-mono">
            {t('keysHint')}
          </span>
        </div>

        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none pb-0.5">
          {DIMENSION_TABS.map((tab) => {
            const TabIcon = tab.icon;
            const isSelected = selectedDimension === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setSelectedDimension(tab.key)}
                className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors whitespace-nowrap ${
                  isSelected
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 shadow-xs'
                    : 'text-zinc-600 hover:bg-zinc-200/60 dark:text-zinc-400 dark:hover:bg-zinc-700/60'
                }`}
              >
                <TabIcon className="h-3 w-3" />
                <span>{t(`dimensions.${tab.key}`)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Suggestion list body */}
      <div className="max-h-64 overflow-y-auto p-1.5 space-y-0.5">
        {isLoading && items.length === 0 ? (
          <div className="flex items-center justify-center py-6 text-xs text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            <span>{t('loading')}</span>
          </div>
        ) : items.length === 0 ? (
          <div className="py-6 text-center text-xs text-zinc-400">
            {t('empty')}
          </div>
        ) : (
          items.map((item, idx) => {
            const isFocused = idx === selectedIndex;
            return (
              <button
                type="button"
                key={`${item.dimension}:${item.target_id}`}
                data-testid={`omni-item-${item.dimension}-${item.target_id}`}
                onClick={() => {
                  onSelectItem(item);
                  closeMenu();
                }}
                onMouseEnter={() => setSelectedIndex(idx)}
                className={`w-full text-left flex items-center justify-between gap-3 rounded-lg px-2.5 py-2 cursor-pointer transition-colors ${
                  isFocused
                    ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
                    : 'text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {getDimensionIcon(item.dimension)}
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate">{item.label}</p>
                    {item.detail && (
                      <p className="text-[11px] text-zinc-400 truncate">{item.detail}</p>
                    )}
                  </div>
                </div>

                <span className="shrink-0 rounded bg-zinc-200/60 px-1.5 py-0.5 text-[10px] font-mono uppercase text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                  @{item.dimension}
                </span>
              </button>
            );
          })
        )}
      </div>
    </dialog>
  );
});

OmniReferenceMenu.displayName = 'OmniReferenceMenu';
