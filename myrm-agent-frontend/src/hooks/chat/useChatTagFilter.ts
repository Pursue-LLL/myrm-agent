/**
 * [INPUT] services/chat::ChatItem (会话实体)
 * [OUTPUT] useChatTagFilter: 管理会话多维度层级标签过滤与统计聚合的状态 Hook
 * [POS] 会话多维度元数据与标签筛选 Hook (Item 156)
 */

import { useState, useMemo, useCallback } from 'react';
import type { ChatItem } from '@/services/chat';

export type TagMatchMode = 'any' | 'all';

export interface TagCountItem {
  tag: string;
  count: number;
}

export interface UseChatTagFilterOptions {
  initialTags?: string[];
  initialMatchMode?: TagMatchMode;
}

export interface UseChatTagFilterReturn {
  selectedTags: string[];
  matchMode: TagMatchMode;
  setMatchMode: (mode: TagMatchMode) => void;
  toggleTag: (tag: string) => void;
  selectTag: (tag: string) => void;
  removeTag: (tag: string) => void;
  clearTags: () => void;
  filterChats: (chats: ChatItem[]) => ChatItem[];
  availableTags: TagCountItem[];
}

export function useChatTagFilter(
  chats: ChatItem[] = [],
  options: UseChatTagFilterOptions = {},
): UseChatTagFilterReturn {
  const [selectedTags, setSelectedTags] = useState<string[]>(options.initialTags ?? []);
  const [matchMode, setMatchMode] = useState<TagMatchMode>(options.initialMatchMode ?? 'any');

  const toggleTag = useCallback((tag: string) => {
    const normalized = tag.trim().replace(/^#/, '');
    if (!normalized) return;
    setSelectedTags((prev) =>
      prev.includes(normalized) ? prev.filter((t) => t !== normalized) : [...prev, normalized],
    );
  }, []);

  const selectTag = useCallback((tag: string) => {
    const normalized = tag.trim().replace(/^#/, '');
    if (!normalized) return;
    setSelectedTags((prev) => (prev.includes(normalized) ? prev : [...prev, normalized]));
  }, []);

  const removeTag = useCallback((tag: string) => {
    const normalized = tag.trim().replace(/^#/, '');
    setSelectedTags((prev) => prev.filter((t) => t !== normalized));
  }, []);

  const clearTags = useCallback(() => {
    setSelectedTags([]);
  }, []);

  const availableTags = useMemo<TagCountItem[]>(() => {
    const map = new Map<string, number>();
    for (const chat of chats) {
      if (Array.isArray(chat.tags)) {
        for (const t of chat.tags) {
          const clean = t.trim().replace(/^#/, '');
          if (clean) {
            map.set(clean, (map.get(clean) ?? 0) + 1);
          }
        }
      }
    }
    return Array.from(map.entries())
      .map(([tag, count]) => ({ tag, count }))
      .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
  }, [chats]);

  const filterChats = useCallback(
    (inputChats: ChatItem[]): ChatItem[] => {
      if (selectedTags.length === 0) {
        return inputChats;
      }
      const targetNormalized = selectedTags.map((t) => t.toLowerCase());

      return inputChats.filter((chat) => {
        const chatTagSet = new Set(
          (chat.tags ?? []).map((t) => t.trim().replace(/^#/, '').toLowerCase()),
        );

        if (matchMode === 'any') {
          return targetNormalized.some((t) => chatTagSet.has(t));
        } else {
          return targetNormalized.every((t) => chatTagSet.has(t));
        }
      });
    },
    [selectedTags, matchMode],
  );

  return {
    selectedTags,
    matchMode,
    setMatchMode,
    toggleTag,
    selectTag,
    removeTag,
    clearTags,
    filterChats,
    availableTags,
  };
}
