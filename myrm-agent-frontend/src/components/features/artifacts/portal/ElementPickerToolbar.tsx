'use client';

/**
 * [INPUT]
 * HtmlPreview postMessage `widget-element-pick` events (via PickedElement);
 * useChatStore::sendMessage (POS: 发送消息到 Agent).
 * [OUTPUT] ElementPickerToolbar: 拾取 DOM 元素后的悬浮提示输入工具栏。
 * [POS] HTML artifact 预览模式的"指哪改哪"UX 增强。
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import useChatStore from '@/store/useChatStore';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import { useMessageQueue } from '@/hooks/useMessageQueue';
import type { PickedElement } from '../renderers/MediaPreview';
import {
  ArrowRight01Icon,
  Cancel01Icon,
} from 'hugeicons-react';

interface ElementPickerToolbarProps {
  pickedElement: PickedElement | null;
  artifactId: string;
  onDismiss: () => void;
}

const MAX_OUTER_HTML_CONTEXT = 600;

const ElementPickerToolbar: React.FC<ElementPickerToolbarProps> = ({ pickedElement, artifactId, onDismiss }) => {
  const t = useTranslations('artifacts.elementPicker');

  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const sendMessage = useChatStore((s) => s.sendMessage);
  const chatId = useChatStore((s) => s.chatId);
  const loading = useChatStore((s) => s.loading);
  const { enqueue } = useMessageQueue(chatId);

  useEffect(() => {
    if (pickedElement && inputRef.current) {
      inputRef.current.focus();
    }
  }, [pickedElement]);

  useEffect(() => {
    setInputValue('');
  }, [pickedElement]);

  const buildElementContext = useCallback(
    (instruction: string): string => {
      if (!pickedElement) return '';

      const truncatedHTML =
        pickedElement.outerHTML.length > MAX_OUTER_HTML_CONTEXT
          ? pickedElement.outerHTML.substring(0, MAX_OUTER_HTML_CONTEXT) + '...'
          : pickedElement.outerHTML;

      return `${instruction}\n\n<element_context artifact_id="${artifactId}" tag="${pickedElement.tagName}" css_selector="${pickedElement.selector}" breadcrumb="${pickedElement.breadcrumb}">\n${truncatedHTML}\n</element_context>`;
    },
    [pickedElement, artifactId],
  );

  const handleSubmit = useCallback(async () => {
    if (!inputValue.trim() || !pickedElement) return;

    const message = buildElementContext(inputValue.trim());
    if (!message) return;

    const dirtyArtifacts = useArtifactPortalStore.getState().getDirtyArtifacts();
    let finalMessage = message;
    for (const [id, content] of Object.entries(dirtyArtifacts)) {
      finalMessage += `\n\n<edited_artifact id="${id}">\n${content}\n</edited_artifact>`;
      useArtifactPortalStore.getState().clearDirtyState(id);
    }

    setInputValue('');
    onDismiss();

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
          console.error('ElementPickerToolbar: failed to send message', err);
        }
      }
    }
  }, [inputValue, pickedElement, buildElementContext, sendMessage, loading, enqueue, onDismiss, t]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      } else if (e.key === 'Escape') {
        onDismiss();
      }
    },
    [handleSubmit, onDismiss],
  );

  if (!pickedElement) return null;

  return (
    <div
      className={cn(
        'absolute bottom-4 left-4 right-4 z-50',
        'animate-in fade-in-0 slide-in-from-bottom-2 duration-200',
      )}
    >
      <div
        className={cn(
          'flex flex-col gap-2 p-3 rounded-xl',
          'bg-popover/95 border border-border shadow-xl backdrop-blur-sm',
        )}
      >
        {/* Breadcrumb display */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0 text-xs text-muted-foreground">
            <span
              className={cn(
                'inline-flex items-center px-1.5 py-0.5 rounded',
                'bg-primary/10 text-primary font-mono text-[10px] font-medium flex-shrink-0',
              )}
            >
              {pickedElement.tagName}
            </span>
            <span className="truncate font-mono text-[10px]">{pickedElement.breadcrumb}</span>
          </div>
          <button
            onClick={onDismiss}
            className="flex-shrink-0 p-0.5 rounded hover:bg-accent transition-colors"
          >
            <Cancel01Icon className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        </div>

        {/* Input row */}
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('placeholder')}
            className={cn(
              'flex-1 min-w-0 bg-transparent text-sm text-popover-foreground',
              'placeholder:text-muted-foreground/60 outline-none',
            )}
          />
          <button
            onClick={handleSubmit}
            disabled={!inputValue.trim()}
            className={cn(
              'flex items-center justify-center w-7 h-7 rounded-full flex-shrink-0',
              'bg-primary text-primary-foreground',
              'hover:bg-primary/90 transition-colors',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            )}
          >
            <ArrowRight01Icon className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ElementPickerToolbar;
