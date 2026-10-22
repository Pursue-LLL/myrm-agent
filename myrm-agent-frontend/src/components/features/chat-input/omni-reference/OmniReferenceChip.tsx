/**
 * [INPUT]
 * - ./omniReferenceTypes::ReferenceDimension
 * - ./omniReferenceTypes::ResolvedContextSlice
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - OmniReferenceChip: Clickable provenance chip rendering 5-dimensional referenced slice badge
 *
 * [POS]
 * Interactive provenance chip rendered in messages or input bar.
 * Strictly adheres to 0-any rule, semantic HTML, < 400 lines limit, and zero native emoji.
 */

'use client';

import React, { useState, memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  FileCode,
  MessageSquare,
  Layers,
  Bot,
  CheckSquare,
  ExternalLink,
  Info,
  X,
} from 'lucide-react';
import type { ReferenceDimension, ResolvedContextSlice } from './omniReferenceTypes';

interface OmniReferenceChipProps {
  dimension: ReferenceDimension;
  targetId: string;
  label: string;
  slice?: ResolvedContextSlice;
  onRemove?: () => void;
  onClick?: () => void;
  className?: string;
}

function getChipIcon(dim: ReferenceDimension): React.ReactElement {
  switch (dim) {
    case 'file':
      return <FileCode className="h-3 w-3 text-sky-500" />;
    case 'session':
      return <MessageSquare className="h-3 w-3 text-emerald-500" />;
    case 'artifact':
      return <Layers className="h-3 w-3 text-indigo-500" />;
    case 'agent':
      return <Bot className="h-3 w-3 text-amber-500" />;
    case 'task':
      return <CheckSquare className="h-3 w-3 text-rose-500" />;
  }
}

export const OmniReferenceChip = memo<OmniReferenceChipProps>(
  ({ dimension, targetId, label, slice, onRemove, onClick, className }) => {
    const t = useTranslations('omniReference');
    const [showPopover, setShowPopover] = useState(false);

    const provenanceUri = slice?.provenance_uri || `myrm://${dimension}/${targetId}`;

    return (
      <span
        data-testid={`omni-chip-${dimension}-${targetId}`}
        className={`relative inline-flex items-center gap-1.5 rounded-md border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-xs text-zinc-700 dark:border-zinc-800 dark:bg-zinc-800/80 dark:text-zinc-300 transition-colors ${
          className || ''
        }`}
      >
        {/* Dimension Icon */}
        {getChipIcon(dimension)}

        {/* Chip Label */}
        <button
          type="button"
          onClick={() => {
            setShowPopover(!showPopover);
            if (onClick) {
              onClick();
            }
          }}
          className="font-medium text-zinc-900 hover:underline dark:text-zinc-100 truncate max-w-40"
          title={provenanceUri}
        >
          {label}
        </button>

        {/* Remove button if removable */}
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            data-testid={`chip-remove-${dimension}-${targetId}`}
            aria-label="Remove reference"
            className="rounded p-0.5 text-zinc-400 hover:bg-zinc-200/60 hover:text-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-zinc-200 transition-colors"
          >
            <X className="h-2.5 w-2.5" />
          </button>
        )}

        {/* Popover Preview for Context Slice and Provenance */}
        {showPopover && (
          <aside
            data-testid="omni-chip-popover"
            aria-label={t('slice.title')}
            className="absolute bottom-full left-0 mb-1 z-50 w-72 rounded-xl border border-zinc-200 bg-white p-3 shadow-xl dark:border-zinc-800 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 text-xs animate-in fade-in zoom-in-95 duration-100"
          >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-100 dark:border-zinc-800 mb-2">
              <div className="flex items-center gap-1.5 font-semibold">
                <Info className="h-3.5 w-3.5 text-amber-500" />
                <span>{t('slice.title')}</span>
              </div>
              <span className="font-mono text-[10px] uppercase text-zinc-400">
                @{dimension}
              </span>
            </div>

            <p className="text-[11px] font-mono text-zinc-600 dark:text-zinc-400 line-clamp-3 bg-zinc-50 dark:bg-zinc-800/60 p-2 rounded border border-zinc-100 dark:border-zinc-800/80 mb-2 whitespace-pre-wrap">
              {slice?.content_slice || `[Referenced ${dimension} entity: ${targetId}]`}
            </p>

            <div className="flex items-center justify-between text-[10px] text-zinc-400">
              <span className="font-mono truncate max-w-44">{provenanceUri}</span>
              <a
                href={provenanceUri}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sky-500 hover:underline"
              >
                <span>{t('slice.provenance')}</span>
                <ExternalLink className="h-2.5 w-2.5" />
              </a>
            </div>
          </aside>
        )}
      </span>
    );
  }
);

OmniReferenceChip.displayName = 'OmniReferenceChip';
