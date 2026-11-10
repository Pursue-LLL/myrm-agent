/**
 * 虚拟列表的滚动监听 Hook
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - @/store/useChatStore (POS: 向上翻页的动作与状态)
 * - zustand/react/shallow::useShallow (POS: 只订阅用到的三项)
 *
 * [OUTPUT]
 * - useVirtualListScroll: 监听滚动容器
 *   - 向上滚动超过 5px 标记用户手动滚动，回到底部附近（100px 内）并向下滚动超过 5px 清除标记
 *   - 距顶部 200px 内且还有更早的消息时加载更早的消息，加载完成后补偿 scrollTop，视口不跳动
 *   - 每次滚动都防抖 200ms 保存滚动镜像
 *   - 返回 loadingOlder：是否正在加载更早的消息
 *
 * [POS]
 * 虚拟列表的滚动意图识别与翻页。输入框草稿等无关的 store 写入不会让列表重新渲染。
 */

'use client';

import { useEffect, useRef } from 'react';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';

interface UseVirtualListScrollOptions {
  /** 列表滚动容器 */
  parentRef: React.RefObject<HTMLDivElement | null>;
  /** 用户是否手动滚动：向上滚动置位，回到底部附近清除 */
  userScrolledRef: React.MutableRefObject<boolean>;
  /** 用户滚动状态变化回调 */
  onUserScrolledChange?: (userScrolled: boolean) => void;
  /** 持久化当前滚动镜像 */
  saveScrollPosition: () => void;
  /** 防抖保存用的定时器句柄 */
  saveTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>;
}

/** 距底部多近算"在底部" */
const NEAR_BOTTOM_PX = 100;
/** 距顶部多近开始加载更早的消息 */
const NEAR_TOP_PX = 200;
/** 小于该位移的滚动不算用户的滚动方向 */
const SCROLL_DIRECTION_JITTER_PX = 5;
/** 滚动停止后保存镜像的防抖时间 */
const SAVE_DEBOUNCE_MS = 200;

export function useVirtualListScroll({
  parentRef,
  userScrolledRef,
  onUserScrolledChange,
  saveScrollPosition,
  saveTimerRef,
}: UseVirtualListScrollOptions): { loadingOlder: boolean } {
  // 只订阅用到的三项：输入框草稿等无关的 store 写入不应该让整张虚拟列表重新渲染
  const { loadOlderMessages, hasMoreMessages, loadingOlder } = useChatStore(
    useShallow((state) => ({
      loadOlderMessages: state.loadOlderMessages,
      hasMoreMessages: state.hasMoreMessages,
      loadingOlder: state.loadingOlder,
    })),
  );
  const loadingOlderRef = useRef(false);
  const lastScrollTopRef = useRef(0);

  useEffect(() => {
    const scrollElement = parentRef.current;
    if (!scrollElement) {
      return;
    }

    lastScrollTopRef.current = scrollElement.scrollTop;

    const handleScroll = () => {
      const currentScrollTop = scrollElement.scrollTop;
      const scrollHeight = scrollElement.scrollHeight;
      const clientHeight = scrollElement.clientHeight;
      const isNearBottom = scrollHeight - currentScrollTop - clientHeight < NEAR_BOTTOM_PX;
      const isNearTop = currentScrollTop < NEAR_TOP_PX;

      const lastScrollTop = lastScrollTopRef.current;

      if (currentScrollTop < lastScrollTop - SCROLL_DIRECTION_JITTER_PX) {
        if (!userScrolledRef.current) {
          userScrolledRef.current = true;
          onUserScrolledChange?.(true);
        }
      }
      if (currentScrollTop > lastScrollTop + SCROLL_DIRECTION_JITTER_PX && isNearBottom) {
        if (userScrolledRef.current) {
          userScrolledRef.current = false;
          onUserScrolledChange?.(false);
        }
      }

      // 防抖保存当前滚动状态镜像
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
      saveTimerRef.current = setTimeout(() => {
        saveScrollPosition();
      }, SAVE_DEBOUNCE_MS);

      if (isNearTop && hasMoreMessages && !loadingOlderRef.current) {
        loadingOlderRef.current = true;
        const prevHeight = scrollHeight;
        loadOlderMessages().finally(() => {
          loadingOlderRef.current = false;
          requestAnimationFrame(() => {
            if (parentRef.current) {
              const newHeight = parentRef.current.scrollHeight;
              parentRef.current.scrollTop = newHeight - prevHeight + currentScrollTop;
            }
          });
        });
      }

      lastScrollTopRef.current = currentScrollTop;
    };

    scrollElement.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      scrollElement.removeEventListener('scroll', handleScroll);
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, [
    parentRef,
    userScrolledRef,
    hasMoreMessages,
    loadOlderMessages,
    onUserScrolledChange,
    saveScrollPosition,
    saveTimerRef,
  ]);

  return { loadingOlder };
}
