'use client';

/**
 * [INPUT]
 * DataGrid / Spreadsheet selection info (row index, sheet name, cell contents);
 * useSelectionAction (POS: 公共消息发送与脏状态同步 hook);
 * useScopedArtifactStore (POS: 局部工件精准编辑状态流).
 * [OUTPUT] SpreadsheetSelectionToolbar: 表格预览与编辑模式下选中的悬浮/内联操作工具栏。
 * [POS] 表格工件定向编辑 UX 增强，让用户可以在选择特定页或数据行后直接引用到输入框进行定向协同。
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { MOBILE_BREAKPOINT } from '@/lib/constants/artifact';
import {
  Edit04Icon,
  InformationCircleIcon,
  Copy01Icon,
  ArrowRight01Icon,
  MessageAdd01Icon,
} from 'hugeicons-react';
import { useSelectionAction } from './useSelectionAction';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import useChatStore from '@/store/useChatStore';

export interface SpreadsheetSelectionToolbarProps {
  visible: boolean;
  position?: { top: number; left: number };
  artifactId?: string;
  filename?: string;
  sheetName?: string;
  selectedRangeLabel: string;
  selectedSnippet: string;
  onClose: () => void;
  className?: string;
}

type ActionType = 'modify' | 'explain' | 'quote';

export const SpreadsheetSelectionToolbar: React.FC<SpreadsheetSelectionToolbarProps> = ({
  visible,
  position,
  artifactId,
  filename,
  sheetName,
  selectedRangeLabel,
  selectedSnippet,
  onClose,
  className,
}) => {
  const t = useTranslations('artifacts.selectionToolbar');
  const [showInput, setShowInput] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const toolbarRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const resetUI = useCallback(() => {
    setShowInput(false);
    setInputValue('');
    onClose();
  }, [onClose]);

  const { sendAction } = useSelectionAction({ onSent: resetUI });

  useEffect(() => {
    if (showInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showInput]);

  const executeAction = useCallback(
    (action: ActionType, customPrompt?: string) => {
      const activeTab = useArtifactPortalStore.getState().getActiveTab();
      const artifactName = filename || activeTab?.title || '表格工件';
      const rangeTag = sheetName ? `${sheetName}!${selectedRangeLabel}` : selectedRangeLabel;

      let message = '';
      if (action === 'modify') {
        const prompt = customPrompt || inputValue.trim();
        if (!prompt) return;
        message = `针对表格「${artifactName}」的范围 (${rangeTag}) 进行修改：\n${prompt}\n\n当前选中数据：\n\`\`\`\n${selectedSnippet}\n\`\`\``;
      } else if (action === 'explain') {
        message = `请分析并解释表格「${artifactName}」中 (${rangeTag}) 的数据：\n\`\`\`\n${selectedSnippet}\n\`\`\``;
      }

      if (!message) return;
      sendAction({ message });
    },
    [filename, sheetName, selectedRangeLabel, inputValue, selectedSnippet, sendAction],
  );

  const handleCopy = useCallback(async () => {
    if (!selectedSnippet) return;
    await writeToClipboard(selectedSnippet);
    onClose();
  }, [selectedSnippet, onClose]);

  const handleQuote = useCallback(() => {
    const activeTab = useArtifactPortalStore.getState().getActiveTab();
    const artifactName = filename || activeTab?.title || '表格工件';
    const targetArtifactId = artifactId || activeTab?.artifactId || 'current';
    const rangeTag = sheetName ? `${sheetName}!${selectedRangeLabel}` : selectedRangeLabel;

    // 1. 设置 ScopedArtifactStore，用于输入框挂载定向编辑芯片
    useScopedArtifactStore.getState().setTarget({
      artifactId: targetArtifactId,
      artifactName,
      kind: 'spreadsheet',
      scopeLabel: rangeTag,
      selectedSnippet: selectedSnippet.replace(/\\t/g, '\t'),
    });

    // 2. 向会话输入框挂载上下文引用
    useChatStore.getState().addMentionReference({
      type: 'artifact_range',
      label: artifactName,
      artifactId: targetArtifactId,
      sheetName,
      range: rangeTag,
      source: 'generated',
      size: selectedSnippet.length,
    });

    onClose();
    const chatInput = document.querySelector('[data-chat-input]') as HTMLElement | null;
    chatInput?.focus();
  }, [artifactId, filename, sheetName, selectedRangeLabel, selectedSnippet, onClose]);

  const handleModifySubmit = useCallback(() => {
    if (!inputValue.trim()) return;
    executeAction('modify', inputValue.trim());
  }, [inputValue, executeAction]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleModifySubmit();
      } else if (e.key === 'Escape') {
        setShowInput(false);
        setInputValue('');
      }
    },
    [handleModifySubmit],
  );

  if (!visible) return null;
  if (typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT) return null;

  return (
    <div
      ref={toolbarRef}
      data-testid="spreadsheet-selection-toolbar"
      className={cn(
        'z-50 animate-in fade-in-0 zoom-in-95 duration-150',
        position ? 'absolute' : 'relative',
        'flex flex-col gap-1',
        className,
      )}
      style={
        position
          ? {
              top: `${position.top}px`,
              left: `${position.left}px`,
              maxWidth: 'calc(100% - 32px)',
            }
          : undefined
      }
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="flex items-center gap-0.5 p-1 rounded-lg bg-background/95 backdrop-blur-md border border-border/80 shadow-lg text-xs">
        {showInput ? (
          <div className="flex items-center gap-1.5 px-1">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('modifyPlaceholder')}
              className="h-6 w-48 px-2 text-xs bg-muted/50 rounded border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button
              onClick={handleModifySubmit}
              disabled={!inputValue.trim()}
              className="p-1 rounded hover:bg-primary/10 text-primary disabled:opacity-40 transition-colors"
              title={t('modify')}
            >
              <ArrowRight01Icon className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => {
                setShowInput(false);
                setInputValue('');
              }}
              className="p-1 rounded hover:bg-muted text-muted-foreground transition-colors text-[11px]"
            >
              取消
            </button>
          </div>
        ) : (
          <>
            <span className="px-2 py-0.5 text-[10px] font-mono font-medium text-primary bg-primary/10 rounded mr-0.5 select-none">
              {sheetName ? `${sheetName}!${selectedRangeLabel}` : selectedRangeLabel}
            </span>
            <button
              onClick={handleQuote}
              className="flex items-center gap-1 px-2 py-1 rounded hover:bg-primary/10 text-primary font-medium transition-colors"
              title="引用到输入框进行定向编辑"
            >
              <MessageAdd01Icon className="w-3.5 h-3.5" />
              <span>引用到输入框</span>
            </button>
            <button
              onClick={() => setShowInput(true)}
              className="flex items-center gap-1 px-2 py-1 rounded hover:bg-muted text-foreground transition-colors"
              title={t('modify')}
            >
              <Edit04Icon className="w-3.5 h-3.5" />
              <span>{t('modify')}</span>
            </button>
            <button
              onClick={() => executeAction('explain')}
              className="flex items-center gap-1 px-2 py-1 rounded hover:bg-muted text-foreground transition-colors"
              title={t('explain')}
            >
              <InformationCircleIcon className="w-3.5 h-3.5" />
              <span>{t('explain')}</span>
            </button>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2 py-1 rounded hover:bg-muted text-foreground transition-colors"
              title={t('copy')}
            >
              <Copy01Icon className="w-3.5 h-3.5" />
              <span>{t('copy')}</span>
            </button>
            <button
              onClick={onClose}
              className="p-1 rounded hover:bg-muted text-muted-foreground transition-colors ml-0.5"
              title="关闭"
            >
              ×
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default SpreadsheetSelectionToolbar;
