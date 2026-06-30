'use client';

/**
 * [INPUT]
 * DOM Selection API (window.getSelection());
 * useSelectionAction (POS: 公共消息发送逻辑);
 * [OUTPUT] DocumentSelectionToolbar: 文档预览模式下选中文本后的悬浮操作工具栏。
 * [POS] DocumentPreview 的选中精准编辑 UX 增强，让非技术用户也能在 Preview 模式下与 Agent 交互。
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { MOBILE_BREAKPOINT } from '@/lib/constants/artifact';
import {
  Edit04Icon,
  InformationCircleIcon,
  SparklesIcon,
  Copy01Icon,
  ArrowRight01Icon,
} from 'hugeicons-react';
import { useSelectionAction } from './useSelectionAction';

interface DocumentSelectionToolbarProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  artifactId?: string;
}

type ActionType = 'modify' | 'explain' | 'optimize';

const TOOLBAR_DEBOUNCE_MS = 250;
const TOOLBAR_HEIGHT_ESTIMATE = 48;

const DocumentSelectionToolbar: React.FC<DocumentSelectionToolbarProps> = ({ containerRef, artifactId }) => {
  const t = useTranslations('artifacts.documentSelection');

  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [selectedText, setSelectedText] = useState('');
  const [showInput, setShowInput] = useState(false);
  const [inputValue, setInputValue] = useState('');

  const toolbarRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hideToolbar = useCallback(() => {
    setVisible(false);
    setShowInput(false);
    setInputValue('');
    setSelectedText('');
  }, []);

  const { sendAction } = useSelectionAction({ onSent: hideToolbar });

  const computePosition = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) {
      hideToolbar();
      return;
    }

    if (!container.contains(selection.anchorNode)) {
      return;
    }

    const text = selection.toString().trim();
    if (!text) {
      hideToolbar();
      return;
    }

    const range = selection.getRangeAt(0);
    const selectionRect = range.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();

    const relativeBottom = selectionRect.bottom - containerRect.top + container.scrollTop;
    const relativeTop = selectionRect.top - containerRect.top + container.scrollTop;
    const relativeLeft = selectionRect.left - containerRect.left;

    const spaceBelow = container.scrollTop + container.clientHeight - relativeBottom;
    const showAbove = spaceBelow < TOOLBAR_HEIGHT_ESTIMATE + 16;

    setSelectedText(text);
    setPosition({
      top: showAbove ? relativeTop - TOOLBAR_HEIGHT_ESTIMATE - 8 : relativeBottom + 8,
      left: Math.max(relativeLeft, 16),
    });
    setVisible(true);
  }, [containerRef, hideToolbar]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleSelectionChange = () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(computePosition, TOOLBAR_DEBOUNCE_MS);
    };

    document.addEventListener('selectionchange', handleSelectionChange);

    return () => {
      document.removeEventListener('selectionchange', handleSelectionChange);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [containerRef, computePosition]);

  useEffect(() => {
    if (showInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showInput]);

  const buildContext = useCallback(
    (actionLabel: string, customInstruction?: string): string => {
      if (!selectedText || !artifactId) return '';

      let instruction = `[${actionLabel}]`;
      if (customInstruction) {
        instruction += `: ${customInstruction}`;
      }

      return `${instruction}\n\n<selection_context artifact_id="${artifactId}" format="document">\n${selectedText}\n</selection_context>`;
    },
    [selectedText, artifactId],
  );

  const executeAction = useCallback(
    (action: ActionType, customInstruction?: string) => {
      if (!selectedText) return;

      const actionLabels: Record<ActionType, string> = {
        modify: t('modify'),
        explain: t('explain'),
        optimize: t('rewrite'),
      };

      const message = buildContext(actionLabels[action], customInstruction);
      if (!message) return;

      sendAction({ message });
    },
    [selectedText, buildContext, sendAction, t],
  );

  const handleCopy = useCallback(async () => {
    if (!selectedText) return;
    await writeToClipboard(selectedText);
    hideToolbar();
  }, [selectedText, hideToolbar]);

  const handleModifyClick = useCallback(() => {
    setShowInput(true);
  }, []);

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

  if (!visible || !selectedText) return null;
  if (typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT) return null;

  const actions: { type: ActionType | 'copy'; icon: React.ReactNode; label: string; onClick: () => void }[] = [
    {
      type: 'modify',
      icon: <Edit04Icon className="w-3.5 h-3.5" />,
      label: t('modify'),
      onClick: handleModifyClick,
    },
    {
      type: 'explain',
      icon: <InformationCircleIcon className="w-3.5 h-3.5" />,
      label: t('explain'),
      onClick: () => executeAction('explain'),
    },
    {
      type: 'optimize',
      icon: <SparklesIcon className="w-3.5 h-3.5" />,
      label: t('rewrite'),
      onClick: () => executeAction('optimize'),
    },
    {
      type: 'copy',
      icon: <Copy01Icon className="w-3.5 h-3.5" />,
      label: t('copy'),
      onClick: handleCopy,
    },
  ];

  return (
    <div
      ref={toolbarRef}
      className={cn('absolute z-50 animate-in fade-in-0 zoom-in-95 duration-150', 'flex flex-col gap-1')}
      style={{
        top: `${position.top}px`,
        left: `${position.left}px`,
        maxWidth: 'calc(100% - 32px)',
      }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <div
        className={cn(
          'flex items-center gap-0.5 px-1 py-0.5 rounded-lg',
          'bg-popover/95 border border-border shadow-lg backdrop-blur-sm',
        )}
      >
        {actions.map((action) => (
          <button
            key={action.type}
            onClick={action.onClick}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium',
              'text-popover-foreground/80 hover:text-popover-foreground',
              'hover:bg-accent transition-colors duration-100',
              action.type === 'modify' && showInput && 'bg-accent text-popover-foreground',
            )}
            title={action.label}
          >
            {action.icon}
            <span className="hidden sm:inline">{action.label}</span>
          </button>
        ))}
      </div>

      {showInput && (
        <div
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg',
            'bg-popover/95 border border-border shadow-lg backdrop-blur-sm',
          )}
        >
          <input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('modifyPlaceholder')}
            className={cn(
              'flex-1 min-w-[200px] bg-transparent text-sm text-popover-foreground',
              'placeholder:text-muted-foreground/60 outline-none',
            )}
          />
          <button
            onClick={handleModifySubmit}
            disabled={!inputValue.trim()}
            className={cn(
              'flex items-center justify-center w-7 h-7 rounded-full',
              'bg-primary text-primary-foreground',
              'hover:bg-primary/90 transition-colors',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            )}
          >
            <ArrowRight01Icon className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};

export default DocumentSelectionToolbar;
