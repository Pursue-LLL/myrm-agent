'use client';

import { useState, useCallback, useMemo } from 'react';
import type { ChatItem } from '@/services/chat';

export type DateGroupKey = 'today' | 'yesterday' | 'prev7days' | 'prev30days' | 'older';

export interface DateGroup {
  key: DateGroupKey;
  items: ChatItem[];
}

const GROUP_ORDER: DateGroupKey[] = ['today', 'yesterday', 'prev7days', 'prev30days', 'older'];

const STORAGE_KEY = 'myrm:sidebar:collapsed-groups';

function computeTimeBoundaries(): {
  todayStart: number;
  yesterdayStart: number;
  prev7Start: number;
  prev30Start: number;
} {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86_400_000;
  const prev7Start = todayStart - 7 * 86_400_000;
  const prev30Start = todayStart - 30 * 86_400_000;
  return { todayStart, yesterdayStart, prev7Start, prev30Start };
}

function classifyDate(ts: number, boundaries: ReturnType<typeof computeTimeBoundaries>): DateGroupKey {
  if (ts >= boundaries.todayStart) return 'today';
  if (ts >= boundaries.yesterdayStart) return 'yesterday';
  if (ts >= boundaries.prev7Start) return 'prev7days';
  if (ts >= boundaries.prev30Start) return 'prev30days';
  return 'older';
}

export function groupChatsByDate(chats: ChatItem[]): DateGroup[] {
  const boundaries = computeTimeBoundaries();
  const buckets = new Map<DateGroupKey, ChatItem[]>();

  for (const chat of chats) {
    const key = classifyDate(chat.updatedAt.getTime(), boundaries);
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.push(chat);
    } else {
      buckets.set(key, [chat]);
    }
  }

  return GROUP_ORDER.filter((key) => buckets.has(key)).map((key) => ({ key, items: buckets.get(key)! }));
}

function readCollapsedState(): Record<string, boolean> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function writeCollapsedState(state: Record<string, boolean>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* quota exceeded — ignore */
  }
}

export function useCollapsedGroups(): {
  collapsed: Record<string, boolean>;
  toggle: (key: string) => void;
} {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(readCollapsedState);

  const toggle = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      writeCollapsedState(next);
      return next;
    });
  }, []);

  return useMemo(() => ({ collapsed, toggle }), [collapsed, toggle]);
}
