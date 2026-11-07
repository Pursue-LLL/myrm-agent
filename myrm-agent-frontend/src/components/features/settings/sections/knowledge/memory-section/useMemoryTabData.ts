/**
 * [INPUT] @/store/memory (POS: 记忆 store), @/services/memory::getMemoryTags (POS: 标签统计), MemoryTabSwitcher::MemoryTab (POS: 标签页标识)
 * [OUTPUT] useMemoryTabData: 当前标签页所需数据的加载、搜索框防抖入库、手动刷新，以及“全部”页的标签筛选项
 * [POS] 记忆面板的数据加载层：登录就绪后拉取待确认记忆；“全部”页拉取记忆与热门标签，“回收站”页拉取归档记忆；搜索输入停顿 300ms 后才写入 store，输入框内容跨标签页保留，与 store 中的查询保持一致。
 */

import { useCallback, useEffect, useState } from 'react';
import type { MemoryTab } from '@/components/features/memory/settings/MemoryTabSwitcher';
import { getMemoryTags, type TagStatsItem } from '@/services/memory';
import { useMemoryStore } from '@/store/memory';

const SEARCH_DEBOUNCE_MS = 300;
const TAG_FILTER_LIMIT = 20;

export function useMemoryTabData(activeTab: MemoryTab, enabled: boolean) {
  const fetchPendingMemories = useMemoryStore((state) => state.fetchPendingMemories);
  const fetchMemories = useMemoryStore((state) => state.fetchMemories);
  const fetchArchivedMemories = useMemoryStore((state) => state.fetchArchivedMemories);
  const memorySearchQuery = useMemoryStore((state) => state.memorySearchQuery);
  const setMemorySearchQuery = useMemoryStore((state) => state.setMemorySearchQuery);
  const [searchInput, setSearchInput] = useState('');
  const [availableTags, setAvailableTags] = useState<TagStatsItem[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    if (enabled) {
      void fetchPendingMemories();
    }
  }, [enabled, fetchPendingMemories]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    if (activeTab === 'all') {
      void fetchMemories();
      getMemoryTags(TAG_FILTER_LIMIT)
        .then((res) => setAvailableTags(res.tags))
        .catch(() => {
          // Tag chips are an optional refinement; without them the list is still fully usable.
        });
    }
    if (activeTab === 'trash') {
      void fetchArchivedMemories();
    }
  }, [activeTab, enabled, fetchMemories, fetchArchivedMemories]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== memorySearchQuery && activeTab === 'all') {
        setMemorySearchQuery(searchInput);
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput, memorySearchQuery, setMemorySearchQuery, activeTab]);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      if (activeTab === 'pending') {
        await fetchPendingMemories();
      } else if (activeTab === 'trash') {
        await fetchArchivedMemories();
      } else {
        await fetchMemories();
      }
    } finally {
      setIsRefreshing(false);
    }
  }, [activeTab, fetchPendingMemories, fetchMemories, fetchArchivedMemories]);

  return { searchInput, setSearchInput, availableTags, isRefreshing, refresh };
}
