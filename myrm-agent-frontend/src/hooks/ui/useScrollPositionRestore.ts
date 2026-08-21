/**
 * [INPUT]
 * - id: string | undefined (POS: 会话/视图唯一标识)
 * - enabled: boolean (POS: 是否开启持久化镜像)
 * - getScrollElement?: () => HTMLElement | Window | null (POS: 滚动宿主获取器，支持 window 或 virtual list div)
 * - onRestore?: (entry: ScrollFollowMirrorEntry) => void (POS: 恢复成功回调)
 *
 * [OUTPUT]
 * - saveScrollPosition: () => void (POS: 即刻同步当前滚动镜像到 L1 内存并在卸载/隐藏/防抖时持久化到 L2 SessionStorage)
 * - restoreScrollPosition: () => boolean (POS: 根据持久化镜像自适应恢复跟随态或视口坐标)
 * - getScrollMirrorSnapshot: () => ScrollFollowMirrorEntry | null (POS: 提取当前会话持久化快照)
 * - userScrolledRef: MutableRefObject<boolean> (POS: 用户是否主动离开底部)
 * - isFollowingBottomRef: MutableRefObject<boolean> (POS: 是否处于流式底部跟随态)
 * - saveTimerRef: MutableRefObject<ReturnType<typeof setTimeout> | null> (POS: 防抖定时器)
 *
 * [POS]
 * AutoScrollFollowPersistenceMirror: 通用滚动跟随持久化镜像总线。
 * 抹平原生 window 与虚拟列表容器差异，实现会话离开 0 延迟镜像、重入 0ms 精确还原。
 */
import { useCallback, useRef, useEffect } from 'react';

const SCROLL_POSITION_KEY_PREFIX = 'myrm_scroll_mirror_';
const MAX_CACHED_SESSIONS = 10;

export interface ScrollFollowMirrorEntry {
  /** 滚动条绝对位置 */
  position: number;
  /** 是否处于底部跟随态 */
  isFollowingBottom: boolean;
  /** 用户是否主动上滑离开底部 */
  isUserScrolledUp: boolean;
  /** 语义锚点消息 ID */
  anchorMessageId?: string;
  /** 更新时间戳 */
  timestamp: number;
}

// L1 内存即时镜像缓存（支持切会话 0ms 瞬间直读）
const inMemoryMirrorMap = new Map<string, ScrollFollowMirrorEntry>();

/**
 * 解析 SessionStorage 缓存数据
 */
const parseScrollMirror = (data: string | null): ScrollFollowMirrorEntry | null => {
  if (!data) {
    return null;
  }
  try {
    const parsed = JSON.parse(data) as Partial<ScrollFollowMirrorEntry>;
    if (typeof parsed?.position !== 'number') {
      return null;
    }
    return {
      position: Math.max(0, parsed.position),
      isFollowingBottom: Boolean(parsed.isFollowingBottom),
      isUserScrolledUp: Boolean(parsed.isUserScrolledUp),
      anchorMessageId: typeof parsed.anchorMessageId === 'string' ? parsed.anchorMessageId : undefined,
      timestamp: typeof parsed.timestamp === 'number' ? parsed.timestamp : Date.now(),
    };
  } catch {
    return null;
  }
};

export interface UseScrollPositionRestoreOptions {
  /** 唯一标识符，用于区分不同的页面/聊天会话 */
  id: string | undefined;
  /** 是否启用滚动位置保存/恢复 */
  enabled?: boolean;
  /** 滚动容器获取器（默认 window） */
  getScrollElement?: () => HTMLElement | Window | null;
  /** 恢复后的回调 */
  onRestore?: (entry: ScrollFollowMirrorEntry) => void;
}

export interface UseScrollPositionRestoreReturn {
  /** 保存当前滚动位置与跟随状态到 L1/L2 镜像 */
  saveScrollPosition: (override?: Partial<ScrollFollowMirrorEntry>) => void;
  /** 恢复滚动位置与跟随状态 */
  restoreScrollPosition: () => boolean;
  /** 获取当前会话的快照 */
  getScrollMirrorSnapshot: () => ScrollFollowMirrorEntry | null;
  /** 标记用户是否已手动滚动（用于配合自动滚动逻辑） */
  userScrolledRef: React.MutableRefObject<boolean>;
  /** 标记是否处于底部跟随态 */
  isFollowingBottomRef: React.MutableRefObject<boolean>;
  /** 用于防抖保存的定时器引用 */
  saveTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>;
}

export function useScrollPositionRestore({
  id,
  enabled = true,
  getScrollElement,
  onRestore,
}: UseScrollPositionRestoreOptions): UseScrollPositionRestoreReturn {
  const hasRestoredRef = useRef(false);
  const userScrolledRef = useRef(false);
  const isFollowingBottomRef = useRef(true);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 获取当前滚动容器与状态
  const resolveScrollMetrics = useCallback(() => {
    const target = getScrollElement ? getScrollElement() : typeof window !== 'undefined' ? window : null;
    if (!target) {
      return { position: 0, scrollHeight: 0, clientHeight: 0, isBottom: true };
    }

    if (target === window || !('scrollTop' in target)) {
      const position = window.scrollY;
      const scrollHeight = document.documentElement.scrollHeight;
      const clientHeight = window.innerHeight;
      const isBottom = scrollHeight - position - clientHeight <= 80;
      return { position, scrollHeight, clientHeight, isBottom };
    }

    const el = target as HTMLElement;
    const position = el.scrollTop;
    const scrollHeight = el.scrollHeight;
    const clientHeight = el.clientHeight;
    const isBottom = scrollHeight - position - clientHeight <= 80;
    return { position, scrollHeight, clientHeight, isBottom };
  }, [getScrollElement]);

  // 保存滚动镜像
  const saveScrollPosition = useCallback(
    (override?: Partial<ScrollFollowMirrorEntry>) => {
      if (!id || !enabled) {
        return;
      }

      const { position, isBottom } = resolveScrollMetrics();
      const isFollowing = override?.isFollowingBottom ?? (isBottom && !userScrolledRef.current);
      const isScrolledUp = override?.isUserScrolledUp ?? userScrolledRef.current;

      const entry: ScrollFollowMirrorEntry = {
        position: override?.position ?? position,
        isFollowingBottom: isFollowing,
        isUserScrolledUp: isScrolledUp,
        anchorMessageId: override?.anchorMessageId,
        timestamp: Date.now(),
      };

      // 1. 同步更新 L1 内存镜像
      inMemoryMirrorMap.set(id, entry);

      // 2. 持久化到 L2 SessionStorage（LRU 维护）
      const key = `${SCROLL_POSITION_KEY_PREFIX}${id}`;
      try {
        sessionStorage.setItem(key, JSON.stringify(entry));

        const allKeys = Object.keys(sessionStorage).filter((k) => k.startsWith(SCROLL_POSITION_KEY_PREFIX));
        if (allKeys.length > MAX_CACHED_SESSIONS) {
          const keyWithTimestamp = allKeys.map((k) => {
            const cache = parseScrollMirror(sessionStorage.getItem(k));
            return { key: k, timestamp: cache?.timestamp || 0 };
          });
          keyWithTimestamp.sort((a, b) => a.timestamp - b.timestamp);

          const keysToRemove = keyWithTimestamp.slice(0, keyWithTimestamp.length - MAX_CACHED_SESSIONS);
          keysToRemove.forEach(({ key: k }) => sessionStorage.removeItem(k));
        }
      } catch {
        // QuotaExceededError 或隐私模式降级
      }
    },
    [id, enabled, resolveScrollMetrics],
  );

  // 获取当前镜像快照
  const getScrollMirrorSnapshot = useCallback((): ScrollFollowMirrorEntry | null => {
    if (!id) {
      return null;
    }
    if (inMemoryMirrorMap.has(id)) {
      return inMemoryMirrorMap.get(id)!;
    }
    try {
      const raw = sessionStorage.getItem(`${SCROLL_POSITION_KEY_PREFIX}${id}`);
      const parsed = parseScrollMirror(raw);
      if (parsed) {
        inMemoryMirrorMap.set(id, parsed);
        return parsed;
      }
    } catch {
      // 忽略
    }
    return null;
  }, [id]);

  // 恢复滚动位置
  const restoreScrollPosition = useCallback((): boolean => {
    if (!id || !enabled || hasRestoredRef.current) {
      return false;
    }

    const snapshot = getScrollMirrorSnapshot();
    hasRestoredRef.current = true;

    if (!snapshot) {
      userScrolledRef.current = false;
      isFollowingBottomRef.current = true;
      return false;
    }

    userScrolledRef.current = snapshot.isUserScrolledUp;
    isFollowingBottomRef.current = snapshot.isFollowingBottom;

    const target = getScrollElement ? getScrollElement() : typeof window !== 'undefined' ? window : null;
    if (!target) {
      onRestore?.(snapshot);
      return true;
    }

    onRestore?.(snapshot);

    // 若离开前为跟随模式，恢复时优先置底
    if (snapshot.isFollowingBottom) {
      requestAnimationFrame(() => {
        if (target === window || !('scrollTop' in target)) {
          window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'auto' });
        } else {
          (target as HTMLElement).scrollTop = (target as HTMLElement).scrollHeight;
        }
      });
      return true;
    }

    // 若离开前为手动查阅模式，恢复绝对位置
    if (snapshot.position > 0) {
      requestAnimationFrame(() => {
        if (target === window || !('scrollTop' in target)) {
          const maxScrollY = document.documentElement.scrollHeight - window.innerHeight;
          window.scrollTo(0, Math.min(snapshot.position, Math.max(0, maxScrollY)));
        } else {
          const el = target as HTMLElement;
          const maxScroll = el.scrollHeight - el.clientHeight;
          el.scrollTop = Math.min(snapshot.position, Math.max(0, maxScroll));
        }
      });
      return true;
    }

    return true;
  }, [id, enabled, getScrollElement, getScrollMirrorSnapshot, onRestore]);

  // id 变化时重置恢复标志
  useEffect(() => {
    hasRestoredRef.current = false;
  }, [id]);

  // 卸载与隐藏时即刻快照
  useEffect(() => {
    if (!id || !enabled) {
      return;
    }

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
      // 仅当已经恢复或主动操作过时才在卸载时保存，避免未恢复的空白挂载覆盖已有快照
      if (hasRestoredRef.current) {
        saveScrollPosition();
      }
    };
  }, [saveScrollPosition, id, enabled]);

  return {
    saveScrollPosition,
    restoreScrollPosition,
    getScrollMirrorSnapshot,
    userScrolledRef,
    isFollowingBottomRef,
    saveTimerRef,
  };
}

export default useScrollPositionRestore;
