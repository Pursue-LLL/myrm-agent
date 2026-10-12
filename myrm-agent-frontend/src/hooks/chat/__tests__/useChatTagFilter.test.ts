import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatTagFilter } from '../useChatTagFilter';
import type { ChatItem } from '@/services/chat';

describe('useChatTagFilter', () => {
  const mockChats: ChatItem[] = [
    {
      id: 'chat-1',
      title: 'Auth Bug Investigation',
      firstMessage: 'Fix token error',
      lastMessage: 'Resolved',
      actionMode: 'fast',
      source: 'web',
      tags: ['BugFix', 'Auth'],
      createdAt: new Date('2026-10-01'),
      updatedAt: new Date('2026-10-01'),
    },
    {
      id: 'chat-2',
      title: 'Billing Module Refactor',
      firstMessage: 'Clean payment pipeline',
      lastMessage: 'Refactored',
      actionMode: 'fast',
      source: 'web',
      tags: ['Refactor', 'Billing'],
      createdAt: new Date('2026-10-02'),
      updatedAt: new Date('2026-10-02'),
    },
    {
      id: 'chat-3',
      title: 'Auth Feature Expansion',
      firstMessage: 'OAuth addition',
      lastMessage: 'Merged',
      actionMode: 'fast',
      source: 'web',
      tags: ['Feature', 'Auth'],
      createdAt: new Date('2026-10-03'),
      updatedAt: new Date('2026-10-03'),
    },
  ];

  it('computes availableTags sorted by popularity and name', () => {
    const { result } = renderHook(() => useChatTagFilter(mockChats));
    expect(result.current.availableTags).toEqual([
      { tag: 'Auth', count: 2 },
      { tag: 'Billing', count: 1 },
      { tag: 'BugFix', count: 1 },
      { tag: 'Feature', count: 1 },
      { tag: 'Refactor', count: 1 },
    ]);
  });

  it('filters chats using union (any) match mode', () => {
    const { result } = renderHook(() => useChatTagFilter(mockChats));

    act(() => {
      result.current.toggleTag('BugFix');
      result.current.toggleTag('Billing');
    });

    const filtered = result.current.filterChats(mockChats);
    expect(filtered.map((c) => c.id)).toEqual(['chat-1', 'chat-2']);
  });

  it('filters chats using intersection (all) match mode', () => {
    const { result } = renderHook(() => useChatTagFilter(mockChats));

    act(() => {
      result.current.setMatchMode('all');
      result.current.toggleTag('#Auth');
      result.current.toggleTag('BugFix');
    });

    const filtered = result.current.filterChats(mockChats);
    expect(filtered.map((c) => c.id)).toEqual(['chat-1']);
  });

  it('clears selected tags correctly', () => {
    const { result } = renderHook(() => useChatTagFilter(mockChats));

    act(() => {
      result.current.selectTag('BugFix');
    });
    expect(result.current.selectedTags).toEqual(['BugFix']);

    act(() => {
      result.current.clearTags();
    });
    expect(result.current.selectedTags).toEqual([]);
    expect(result.current.filterChats(mockChats)).toHaveLength(3);
  });
});
