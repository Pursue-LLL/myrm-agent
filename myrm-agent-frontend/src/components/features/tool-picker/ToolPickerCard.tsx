/**
 * [INPUT]
 * @/hooks/ui/useCategorizedToolPicker::CategorizedToolItem
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - ToolPickerCard: Interactive tool item card with pin toggle and enabled switch
 *
 * [POS]
 * Sub-component for CategorizedToolPickerWithPinningAndInstantFilter (Item 15).
 * Single file < 150 lines. Zero `any` types.
 */

'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import type { CategorizedToolItem } from '@/hooks/ui/useCategorizedToolPicker';

export interface ToolPickerCardProps {
  tool: CategorizedToolItem;
  isPinned: boolean;
  onTogglePin: (id: string) => void;
  onToggleEnabled: (id: string) => void;
  onSelect?: (tool: CategorizedToolItem) => void;
}

export const ToolPickerCard: React.FC<ToolPickerCardProps> = ({
  tool,
  isPinned,
  onTogglePin,
  onToggleEnabled,
  onSelect,
}) => {
  const t = useTranslations('toolPicker');

  const sourceBadgeColor =
    tool.source === 'builtin'
      ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20'
      : tool.source === 'skill'
        ? 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20'
        : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';

  const sourceLabelKey =
    tool.source === 'builtin'
      ? 'sourceBuiltin'
      : tool.source === 'skill'
        ? 'sourceSkill'
        : 'sourceMcp';

  return (
    <div className="group flex flex-col justify-between p-3 rounded-2xl border border-zinc-200/80 bg-white/90 hover:bg-zinc-50 hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:bg-zinc-800/80 transition-all shadow-sm hover:shadow">
      <div>
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <button
            type="button"
            onClick={() => onSelect?.(tool)}
            className="flex items-center gap-2 min-w-0 text-left flex-1 focus:outline-none cursor-pointer"
          >
            <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 truncate">
              {tool.displayName}
            </span>
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full border font-mono uppercase ${sourceBadgeColor}`}
            >
              {t(sourceLabelKey)}
            </span>
          </button>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onTogglePin(tool.id);
              }}
              title={isPinned ? t('unpinTool') : t('pinTool')}
              aria-label={isPinned ? t('unpinTool') : t('pinTool')}
              className={`p-1 rounded-lg transition-colors ${
                isPinned
                  ? 'text-amber-500 bg-amber-500/10'
                  : 'text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 dark:hover:text-zinc-200'
              }`}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill={isPinned ? 'currentColor' : 'none'}
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="12" y1="17" x2="12" y2="22" />
                <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z" />
              </svg>
            </button>
          </div>
        </div>

        <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2 leading-relaxed">
          {tool.description}
        </p>
      </div>

      <div className="flex items-center justify-between mt-3 pt-2 border-t border-zinc-100 dark:border-zinc-800/80">
        <code className="text-[11px] text-zinc-400 dark:text-zinc-500 font-mono truncate max-w-[150px]">
          {tool.name}
        </code>

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {tool.enabled ? t('enabled') : t('disabled')}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleEnabled(tool.id);
            }}
            aria-label={`${tool.displayName} ${tool.enabled ? t('enabled') : t('disabled')}`}
            className={`w-8 h-4.5 rounded-full transition-colors relative flex items-center p-0.5 ${
              tool.enabled
                ? 'bg-emerald-500'
                : 'bg-zinc-300 dark:bg-zinc-700'
            }`}
          >
            <span
              className={`w-3.5 h-3.5 rounded-full bg-white shadow-sm transition-transform ${
                tool.enabled ? 'translate-x-3.5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  );
};
