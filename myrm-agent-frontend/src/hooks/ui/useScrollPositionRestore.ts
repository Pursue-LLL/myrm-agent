import { useCallback, useRef, useEffect } from 'react';
import { isNearBottom } from '@/lib/utils/domUtils';

// 滚动位置存储的键名前缀
const SCROLL_POSITION_KEY_PREFIX = 'chat_scroll_';
// 最大缓存的聊天数量
const MAX_CACHED_CHATS = 5;

// 滚动位置缓存数据结构
interface ScrollPositionCache {
  position: number;
  timestamp: number;
}

// 解析缓存数据
const parseScrollCache = (data: string | null): ScrollPositionCache | null => {
  if (!data) return null;
  try {
    // 兼容旧格式（纯数字）
    if (!data.startsWith('{')) {
      const position = parseInt(data, 10);
      return isNaN(position) ? null : { position, timestamp: Date.now() };
    }
    return JSON.parse(data) as ScrollPositionCache;
  } catch {
    return null;
  }
};

interface UseScrollPositionRestoreOptions {
  /** 唯一标识符，用于区分不同的页面/聊天 */
  id: string | undefined;
  /** 是否启用滚动位置保存/恢复 */
  enabled?: boolean;
  /** 恢复后的回调 */
  onRestore?: (position: number) => void;
}

interface UseScrollPositionRestoreReturn {
  /** 保存当前滚动位置 */
  saveScrollPosition: () => void;
  /** 恢复滚动位置 */
  restoreScrollPosition: () => void;
  /** 标记用户是否已手动滚动（用于配合自动滚动逻辑） */
  userScrolledRef: React.MutableRefObject<boolean>;
  /** 用于防抖保存的定时器引用 */
  saveTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>;
}

/**
 * 滚动位置保存和恢复的自定义 Hook
 *
 * 功能：
 * 1. 在滚动时自动保存位置到 sessionStorage（防抖）
 * 2. 页面卸载/隐藏时立即保存
 * 3. 组件挂载时自动恢复滚动位置
 * 4. 自动清理过期缓存（保留最近 N 个）
 */
export function useScrollPositionRestore({
  id,
  enabled = true,
  onRestore,
}: UseScrollPositionRestoreOptions): UseScrollPositionRestoreReturn {
  const hasRestoredRef = useRef(false);
  const userScrolledRef = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 保存滚动位置到 sessionStorage
  const saveScrollPosition = useCallback(() => {
    if (!id || !enabled) return;

    const scrollPosition = window.scrollY;
    const key = `${SCROLL_POSITION_KEY_PREFIX}${id}`;

    try {
      // 保存当前聊天的滚动位置（包含时间戳）
      const cacheData: ScrollPositionCache = {
        position: scrollPosition,
        timestamp: Date.now(),
      };
      sessionStorage.setItem(key, JSON.stringify(cacheData));

      // 清理旧的缓存，只保留最近的 N 个聊天的滚动位置
      const allKeys = Object.keys(sessionStorage).filter((k) => k.startsWith(SCROLL_POSITION_KEY_PREFIX));
      if (allKeys.length > MAX_CACHED_CHATS) {
        // 按时间戳排序，移除最旧的缓存
        const keyWithTimestamp = allKeys.map((k) => {
          const cache = parseScrollCache(sessionStorage.getItem(k));
          return { key: k, timestamp: cache?.timestamp || 0 };
        });
        keyWithTimestamp.sort((a, b) => a.timestamp - b.timestamp);

        // 移除最旧的缓存，保留最新的 MAX_CACHED_CHATS 个
        const keysToRemove = keyWithTimestamp.slice(0, keyWithTimestamp.length - MAX_CACHED_CHATS);
        keysToRemove.forEach(({ key: k }) => sessionStorage.removeItem(k));
      }
    } catch {
      // sessionStorage 可能已满或不可用，忽略错误
    }
  }, [id, enabled]);

  // 恢复滚动位置
  const restoreScrollPosition = useCallback(() => {
    if (!id || !enabled || hasRestoredRef.current) return;

    const key = `${SCROLL_POSITION_KEY_PREFIX}${id}`;

    try {
      const cache = parseScrollCache(sessionStorage.getItem(key));
      if (cache && cache.position > 0) {
        // 使用 requestAnimationFrame 确保 DOM 已经渲染完成
        requestAnimationFrame(() => {
          // 计算页面最大可滚动距离
          const maxScrollY = document.documentElement.scrollHeight - window.innerHeight;
          // 确保不超过最大可滚动距离
          const targetPosition = Math.min(cache.position, Math.max(0, maxScrollY));

          if (targetPosition > 0) {
            window.scrollTo(0, targetPosition);
            // 标记用户已经滚动过（如果恢复的位置不在底部）
            if (!isNearBottom()) {
              userScrolledRef.current = true;
            }
            onRestore?.(targetPosition);
          }
          hasRestoredRef.current = true;
        });
      } else {
        hasRestoredRef.current = true;
      }
    } catch {
      // sessionStorage 不可用，忽略错误
      hasRestoredRef.current = true;
    }
  }, [id, enabled, onRestore]);

  // id 变化时重置恢复标志
  useEffect(() => {
    hasRestoredRef.current = false;
  }, [id]);

  // 页面卸载或隐藏时立即保存滚动位置
  useEffect(() => {
    if (!id || !enabled) return;

    const handleBeforeUnload = () => saveScrollPosition();
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        saveScrollPosition();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [saveScrollPosition, id, enabled]);

  return {
    saveScrollPosition,
    restoreScrollPosition,
    userScrolledRef,
    saveTimerRef,
  };
}

export default useScrollPositionRestore;
