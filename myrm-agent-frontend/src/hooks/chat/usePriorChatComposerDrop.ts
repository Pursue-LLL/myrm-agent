'use client';

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  PRIOR_CHAT_DRAG_MIME,
  buildPriorChatMention,
  decodePriorChatDragPayload,
  hasPriorChatDragType,
} from '@/lib/chat/priorChatDrag';
import useChatStore from '@/store/useChatStore';
import type { DragHandlers } from '@/hooks/ui/useDragDrop';

export interface UsePriorChatComposerDropOptions {
  disabled?: boolean;
}

export interface UsePriorChatComposerDropReturn {
  isSessionDragging: boolean;
  dragHandlers: DragHandlers;
}

export function usePriorChatComposerDrop(
  options: UsePriorChatComposerDropOptions = {},
): UsePriorChatComposerDropReturn {
  const { disabled = false } = options;
  const tSearch = useTranslations('search');
  const [isSessionDragging, setIsSessionDragging] = useState(false);
  const dragCounter = useRef(0);

  const handleDragEnter = useCallback(
    (event: React.DragEvent) => {
      if (disabled || !hasPriorChatDragType(event.dataTransfer)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      dragCounter.current += 1;
      setIsSessionDragging(true);
    },
    [disabled],
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent) => {
      if (disabled || !hasPriorChatDragType(event.dataTransfer)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = 'copy';
    },
    [disabled],
  );

  const handleDragLeave = useCallback(
    (event: React.DragEvent) => {
      if (disabled) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      dragCounter.current = Math.max(0, dragCounter.current - 1);
      if (dragCounter.current === 0) {
        setIsSessionDragging(false);
      }
    },
    [disabled],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      if (disabled) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      dragCounter.current = 0;
      setIsSessionDragging(false);

      if (!hasPriorChatDragType(event.dataTransfer)) {
        return;
      }

      const raw = event.dataTransfer.getData(PRIOR_CHAT_DRAG_MIME);
      const payload = decodePriorChatDragPayload(raw);
      if (!payload) {
        return;
      }

      const composerChatId = useChatStore.getState().chatId;
      if (composerChatId && composerChatId === payload.chatId) {
        toast.info(tSearch('citeSameChat'));
        return;
      }

      useChatStore.getState().addMentionReference(buildPriorChatMention(payload));

      window.setTimeout(() => {
        const inputElement = document.querySelector('[data-chat-input]');
        if (inputElement instanceof HTMLTextAreaElement) {
          inputElement.focus();
        }
      }, 50);
    },
    [disabled, tSearch],
  );

  return {
    isSessionDragging,
    dragHandlers: {
      onDragEnter: handleDragEnter,
      onDragOver: handleDragOver,
      onDragLeave: handleDragLeave,
      onDrop: handleDrop,
    },
  };
}
