'use client';

import React, { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { MessageAdd01Icon, Copy01Icon, Cancel01Icon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';

export interface SpreadsheetSelectionToolbarProps {
  selectedRowIndex: number | null;
  headers: string[];
  rowData: string[] | null;
  filename?: string;
  sheetName?: string;
  onClearSelection: () => void;
}

export const SpreadsheetSelectionToolbar: React.FC<SpreadsheetSelectionToolbarProps> = ({
  selectedRowIndex,
  headers,
  rowData,
  filename,
  sheetName,
  onClearSelection,
}) => {
  const t = useTranslations('artifacts.spreadsheet');

  const handleQuote = useCallback(() => {
    if (selectedRowIndex === null || !rowData) return;

    const activeTab = useArtifactPortalStore.getState().getActiveTab();
    const artifactName = filename || activeTab?.title || '表格工件';
    const artifactId = activeTab?.artifactId || 'current';
    const rowNum = selectedRowIndex + 1;
    const scopeLabel = sheetName ? `${sheetName}!Row ${rowNum}` : `Row ${rowNum}`;

    const selectedSnippet = headers
      .map((header, idx) => {
        const val = rowData[idx] ?? '';
        return `${header || `Col ${idx + 1}`}: ${val}`;
      })
      .join(', ');

    useScopedArtifactStore.getState().setTarget({
      artifactId,
      artifactName,
      kind: 'spreadsheet',
      scopeLabel,
      selectedSnippet,
    });

    const chatInput = document.querySelector('[data-chat-input]') as HTMLElement | null;
    chatInput?.focus();
  }, [selectedRowIndex, rowData, filename, sheetName, headers]);

  const handleCopy = useCallback(async () => {
    if (selectedRowIndex === null || !rowData) return;
    const headerLine = headers.join('\t');
    const dataLine = rowData.join('\t');
    await writeToClipboard(`${headerLine}\n${dataLine}`);
  }, [selectedRowIndex, rowData, headers]);

  if (selectedRowIndex === null || !rowData) {
    return null;
  }

  const rowNum = selectedRowIndex + 1;
  const label = sheetName ? `${sheetName}!Row ${rowNum}` : `Row ${rowNum}`;

  return (
    <div
      data-testid="spreadsheet-selection-toolbar"
      className={cn(
        'absolute bottom-4 left-1/2 -translate-x-1/2 z-30',
        'flex items-center gap-1.5 px-3 py-1.5 rounded-full',
        'bg-popover/95 border border-border shadow-lg backdrop-blur-sm',
        'animate-in fade-in-0 zoom-in-95 duration-150',
      )}
      onMouseDown={(e) => e.preventDefault()}
    >
      <span className="text-xs font-medium text-foreground px-1 select-none">
        {label}
      </span>
      <div className="h-3.5 w-px bg-border mx-0.5" />
      <button
        type="button"
        onClick={handleQuote}
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium',
          'text-popover-foreground/80 hover:text-popover-foreground hover:bg-accent transition-colors',
        )}
        title={t('quote') || '引用到输入框'}
      >
        <MessageAdd01Icon className="w-3.5 h-3.5 text-primary" />
        <span>{t('quote') || '引用到输入框'}</span>
      </button>
      <button
        type="button"
        onClick={handleCopy}
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium',
          'text-popover-foreground/80 hover:text-popover-foreground hover:bg-accent transition-colors',
        )}
        title={t('copy') || '复制行'}
      >
        <Copy01Icon className="w-3.5 h-3.5" />
        <span>{t('copy') || '复制'}</span>
      </button>
      <button
        type="button"
        onClick={onClearSelection}
        className="p-1 rounded-full text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        aria-label="Clear selection"
      >
        <Cancel01Icon className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

export default SpreadsheetSelectionToolbar;
