/**
 * [INPUT]
 * - MentionReference (store/chat/types/messages)
 *
 * [OUTPUT]
 * - PRIOR_CHAT_DRAG_MIME: HTML5 drag MIME for sidebar session → composer cite.
 * - encode/decode PriorChatDragPayload helpers.
 *
 * [POS]
 * Shared payload contract for Tauri/desktop session drag-to-composer (#5b).
 * Reuses the same prior_chat mention SSOT as @chat: picker and Cmd+K cite.
 */

import type { DragEvent } from 'react';

import type { MentionReference } from '@/store/chat/types/messages';

export const PRIOR_CHAT_DRAG_MIME = 'application/x-myrm-prior-chat+json';

export interface PriorChatDragPayload {
  chatId: string;
  title: string;
}

export function encodePriorChatDragPayload(payload: PriorChatDragPayload): string {
  return JSON.stringify(payload);
}

export function decodePriorChatDragPayload(raw: string): PriorChatDragPayload | null {
  try {
    const parsed = JSON.parse(raw) as Partial<PriorChatDragPayload>;
    const chatId = typeof parsed.chatId === 'string' ? parsed.chatId.trim() : '';
    if (!chatId) {
      return null;
    }
    const titleRaw = typeof parsed.title === 'string' ? parsed.title.trim() : '';
    return {
      chatId,
      title: titleRaw || 'Untitled conversation',
    };
  } catch {
    return null;
  }
}

export function hasPriorChatDragType(dataTransfer: DataTransfer): boolean {
  return Array.from(dataTransfer.types).includes(PRIOR_CHAT_DRAG_MIME);
}

export function buildPriorChatMention(payload: PriorChatDragPayload): MentionReference {
  return {
    type: 'prior_chat',
    label: `@chat:${payload.title}`,
    path: payload.chatId,
    fileId: payload.chatId,
    source: 'special',
  };
}

export function createPriorChatDragStartHandler(chat: { id: string; title: string }) {
  return (event: DragEvent<HTMLElement>) => {
    event.stopPropagation();
    event.dataTransfer.clearData();
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData(
      PRIOR_CHAT_DRAG_MIME,
      encodePriorChatDragPayload({ chatId: chat.id, title: chat.title }),
    );
  };
}
