'use client';

/**
 * [INPUT]
 * Monaco Editor selection events (onDidChangeCursorSelection);
 * useArtifactPortalStore::dirtyArtifacts (POS: 协同编辑脏状态);
 * useChatStore::sendMessage (POS: 发送消息到 Agent).
 * [OUTPUT] SelectionToolbar: 选中文本后的悬浮操作工具栏。
 * [POS] Portal 内 Monaco Editor 的选中精准编辑 UX 增强。
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import type { editor } from 'monaco-editor';
import { cn } from '@/lib/utils/classnameUtils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { MOBILE_BREAKPOINT } from '@/lib/constants/artifact';
import { toast } from '@/lib/utils/toast';
import useChatStore from '@/store/useChatStore';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import { useMessageQueue } from '@/hooks/useMessageQueue';
import {
  Edit04Icon,
  InformationCircleIcon,
  SparklesIcon,
  MessageAdd01Icon,
  Copy01Icon,
  ArrowRight01Icon,
} from 'hugeicons-react';

interface SelectionInfo {
  text: string;
  startLine: number;
  endLine: number;
}

interface SelectionToolbarProps {
  editorInstance: editor.IStandaloneCodeEditor | null;
  artifactId?: string;
  language?: string;
}

type ActionType = 'modify' | 'explain' | 'optimize' | 'comment';

const TOOLBAR_DEBOUNCE_MS = 200;

const TOOLBAR_HEIGHT_ESTIMATE = 48;

const SelectionToolbar: React.FC<SelectionToolbarProps> = ({ editorInstance, artifactId, language }) => {
  const t = useTranslations('artifacts.selectionToolbar');

  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [selection, setSelection] = useState<SelectionInfo | null>(null);
  const [showInput, setShowInput] = useState(false);
  const [inputValue, setInputValue] = useState('');

  const toolbarRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sendMessage = useChatStore((s) => s.sendMessage);
  const chatId = useChatStore((s) => s.chatId);
  const loading = useChatStore((s) => s.loading);
  const { enqueue } = useMessageQueue(chatId);

  useEffect(() => {
    if (!editorInstance) return;

    const hideToolbar = () => {
      setVisible(false);
      setShowInput(false);
      setInputValue('');
    };

    const computePosition = () => {
      const sel = editorInstance.getSelection();
      if (!sel || sel.isEmpty()) {
        hideToolbar();
        return;
      }

      const model = editorInstance.getModel();
      if (!model) return;

      const selectedText = model.getValueInRange(sel);
      if (!selectedText.trim()) {
        setVisible(false);
        return;
      }

      const endPos = editorInstance.getScrolledVisiblePosition({
        lineNumber: sel.endLineNumber,
        column: sel.endColumn,
      });

      if (!endPos) {
        setVisible(false);
        return;
      }

      const editorDom = editorInstance.getDomNode();
      const editorHeight = editorDom?.clientHeight ?? 600;
      const spaceBelow = editorHeight - (endPos.top + endPos.height);
      const showAbove = spaceBelow < TOOLBAR_HEIGHT_ESTIMATE + 16;

      const startPos = editorInstance.getScrolledVisiblePosition({
        lineNumber: sel.startLineNumber,
        column: sel.startColumn,
      });

      setSelection({
        text: selectedText,
        startLine: sel.startLineNumber,
        endLine: sel.endLineNumber,
      });

      if (showAbove && startPos) {
        setPosition({
          top: startPos.top - TOOLBAR_HEIGHT_ESTIMATE - 8,
          left: Math.max(startPos.left, 16),
        });
      } else {
        setPosition({
          top: endPos.top + endPos.height + 8,
          left: Math.max(endPos.left, 16),
        });
      }
      setVisible(true);
    };

    const selectionDisposable = editorInstance.onDidChangeCursorSelection(() => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(computePosition, TOOLBAR_DEBOUNCE_MS);
    });

    const scrollDisposable = editorInstance.onDidScrollChange(() => {
      if (visible) setVisible(false);
    });

    return () => {
      selectionDisposable.dispose();
      scrollDisposable.dispose();
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [editorInstance, visible]);

  useEffect(() => {
    if (showInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showInput]);

  const buildSelectionContext = useCallback(
    (actionLabel: string, customInstruction?: string): string => {
      if (!selection || !artifactId) return '';

      const lineRange =
        selection.startLine === selection.endLine
          ? `line ${selection.startLine}`
          : `lines ${selection.startLine}-${selection.endLine}`;

      let instruction = `[${actionLabel}] ${lineRange}`;
      if (customInstruction) {
        instruction += `: ${customInstruction}`;
      }

      return `${instruction}\n\n<selection_context artifact_id="${artifactId}" language="${language || 'unknown'}" start_line="${selection.startLine}" end_line="${selection.endLine}">\n${selection.text}\n</selection_context>`;
    },
    [selection, artifactId, language],
  );

  const executeAction = useCallback(
    async (action: ActionType, customInstruction?: string) => {
      if (!selection) return;

      const actionLabels: Record<ActionType, string> = {
        modify: t('modify'),
        explain: t('explain'),
        optimize: t('optimize'),
        comment: t('addComment'),
      };

      const message = buildSelectionContext(actionLabels[action], customInstruction);
      if (!message) return;

      const dirtyArtifacts = useArtifactPortalStore.getState().getDirtyArtifacts();
      let finalMessage = message;
      for (const [id, content] of Object.entries(dirtyArtifacts)) {
        finalMessage += `\n\n<edited_artifact id="${id}">\n${content}\n</edited_artifact>`;
        useArtifactPortalStore.getState().clearDirtyState(id);
      }

      setVisible(false);
      setShowInput(false);
      setInputValue('');

      if (loading) {
        enqueue(finalMessage, []);
        toast.info(t('queued'));
      } else {
        try {
          await sendMessage(finalMessage, undefined);
        } catch (err) {
          if (err && typeof err === 'object' && 'name' in err && err.name === 'AgentBusyError') {
            enqueue(finalMessage, []);
            toast.info(t('queued'));
          } else {
            console.error('SelectionToolbar: failed to send message', err);
          }
        }
      }
    },
    [selection, buildSelectionContext, sendMessage, loading, enqueue, t],
  );

  const handleCopy = useCallback(async () => {
    if (!selection) return;
    await writeToClipboard(selection.text);
    setVisible(false);
  }, [selection]);

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

  if (!visible || !selection) return null;
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
      label: t('optimize'),
      onClick: () => executeAction('optimize'),
    },
    {
      type: 'comment',
      icon: <MessageAdd01Icon className="w-3.5 h-3.5" />,
      label: t('addComment'),
      onClick: () => executeAction('comment'),
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

export default SelectionToolbar;
