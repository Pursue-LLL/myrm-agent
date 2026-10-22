/**
 * [INPUT] rawText to extract, optional onExtract callback, optional compact mode
 * [OUTPUT] SmartTaskExtractionButton component stripping fluff and filling task draft
 * [POS] task-action-preview/SmartTaskExtractionButton.tsx
 */

'use client';

import React, { useState, useCallback } from 'react';
import { ListPlus, Check, Sparkles } from 'lucide-react';
import { extractCleanedActionItem } from './smartFluffStripper';
import type { CleanedActionItem } from './taskActionPreviewTypes';

export interface SmartTaskExtractionButtonProps {
  rawText: string;
  onExtract?: (item: CleanedActionItem) => void;
  className?: string;
  compact?: boolean;
  disabled?: boolean;
  testId?: string;
}

export const SmartTaskExtractionButton: React.FC<SmartTaskExtractionButtonProps> = ({
  rawText,
  onExtract,
  className = '',
  compact = false,
  disabled = false,
  testId = 'smart-task-extraction-btn',
}) => {
  const [extractedRecently, setExtractedRecently] = useState<boolean>(false);

  const handleExtract = useCallback(() => {
    if (disabled || !rawText.trim()) {
      return;
    }

    const cleanedItem = extractCleanedActionItem(rawText);

    if (onExtract) {
      onExtract(cleanedItem);
    }

    // Dispatch global custom event for decoupled composer injection
    if (typeof window !== 'undefined') {
      const event = new CustomEvent('myrm:inject-composer-task', {
        detail: cleanedItem,
        bubbles: true,
      });
      window.dispatchEvent(event);
    }

    setExtractedRecently(true);
    setTimeout(() => {
      setExtractedRecently(false);
    }, 2000);
  }, [disabled, rawText, onExtract]);

  const buttonTitle = extractedRecently
    ? '已提炼并填入任务草稿'
    : '一键去除寒暄客套，智能提取为结构化待办 Task';

  return (
    <button
      type="button"
      data-testid={testId}
      onClick={handleExtract}
      disabled={disabled || !rawText.trim()}
      title={buttonTitle}
      aria-label={buttonTitle}
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-all ${
        extractedRecently
          ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
          : 'bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40'
      } disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    >
      {extractedRecently ? (
        <Check className="h-3.5 w-3.5 text-emerald-500 animate-in fade-in" />
      ) : (
        <Sparkles className="h-3.5 w-3.5 text-primary" />
      )}
      {!compact && (
        <span className="flex items-center gap-1">
          {extractedRecently ? '已转 Task' : '转为 Task'}
          {!extractedRecently && <ListPlus className="h-3 w-3 opacity-70" />}
        </span>
      )}
    </button>
  );
};
