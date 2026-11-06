/**
 * [INPUT]
 * - react (POS: 状态、引用与定时器)
 *
 * [OUTPUT]
 * - useHistorySearch: 侧栏会话搜索框的开合、输入回显与防抖提交。
 * - HistorySearch: useHistorySearch 的返回值类型，交给搜索工具栏渲染。
 *
 * [POS]
 * 输入先回显在本地，停顿 `SEARCH_DEBOUNCE_MS` 后才把关键词交给调用方去筛选历史（避免每个按键一次请求）；
 * 打开搜索框时聚焦输入，关闭时若还留着关键词则一并清空。
 */
import { useCallback, useEffect, useRef, useState } from 'react';

const SEARCH_DEBOUNCE_MS = 300;

export function useHistorySearch(appliedKeyword: string, applyKeyword: (keyword: string) => void) {
  const [showSearch, setShowSearch] = useState(false);
  const [localKeyword, setLocalKeyword] = useState(appliedKeyword);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const handleSearchChange = useCallback(
    (value: string) => {
      setLocalKeyword(value);
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        applyKeyword(value);
      }, SEARCH_DEBOUNCE_MS);
    },
    [applyKeyword],
  );

  const handleClearSearch = useCallback(() => {
    setLocalKeyword('');
    applyKeyword('');
    setShowSearch(false);
  }, [applyKeyword]);

  const handleToggleSearch = useCallback(() => {
    const next = !showSearch;
    setShowSearch(next);
    if (next) {
      requestAnimationFrame(() => searchInputRef.current?.focus());
    } else if (localKeyword) {
      handleClearSearch();
    }
  }, [showSearch, localKeyword, handleClearSearch]);

  return { showSearch, localKeyword, searchInputRef, handleSearchChange, handleClearSearch, handleToggleSearch };
}

export type HistorySearch = ReturnType<typeof useHistorySearch>;
