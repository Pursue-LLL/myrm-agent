/**
 * 横向标签栏末尾项自动揭示与溢出感知 Hook
 *
 * 监听激活 tab 变更与视口尺寸波动，对标 penguin-harness #4152 保证最后一项与右侧操作按钮不被裁切。
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import type { TabRevealOptions, TabStripOverflowState } from './modelPickerKeyboardTypes';
import {
  DEFAULT_TAB_SAFE_MARGIN_PX,
  calculateScrollRevealOffset,
  detectTabStripOverflow,
} from './modelPickerKeyboardEngine';

export interface UseTabStripRevealOptions {
  activeTabId?: string;
  safeMarginPx?: number;
  behavior?: ScrollBehavior;
}

export function useTabStripReveal(options?: UseTabStripRevealOptions) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [overflowState, setOverflowState] = useState<TabStripOverflowState>({
    isOverflowing: false,
    canScrollLeft: false,
    canScrollRight: false,
    scrollLeft: 0,
    maxScrollLeft: 0,
  });

  const updateOverflow = useCallback(() => {
    const el = containerRef.current;
    if (!el) {
      return;
    }
    const state = detectTabStripOverflow(el.scrollWidth, el.clientWidth, el.scrollLeft);
    setOverflowState(state);
  }, []);

  const revealElement = useCallback(
    (targetEl: HTMLElement, overrideOptions?: TabRevealOptions) => {
      const container = containerRef.current;
      if (!container) {
        return;
      }

      const containerRect = container.getBoundingClientRect();
      const targetRect = targetEl.getBoundingClientRect();
      const behavior = overrideOptions?.behavior ?? options?.behavior ?? 'smooth';
      const safeMargin = overrideOptions?.safeMarginPx ?? options?.safeMarginPx ?? DEFAULT_TAB_SAFE_MARGIN_PX;

      const targetScrollLeft = calculateScrollRevealOffset(
        containerRect,
        targetRect,
        container.scrollLeft,
        {
          safeMarginPx: safeMargin,
          revealPosition: overrideOptions?.revealPosition ?? 'nearest',
        },
      );

      if (Math.abs(targetScrollLeft - container.scrollLeft) > 1) {
        if (typeof container.scrollTo === 'function') {
          container.scrollTo({
            left: targetScrollLeft,
            behavior,
          });
        } else {
          container.scrollLeft = targetScrollLeft;
        }
      }
    },
    [options?.behavior, options?.safeMarginPx],
  );

  const revealTabById = useCallback(
    (tabId: string, overrideOptions?: TabRevealOptions) => {
      const container = containerRef.current;
      if (!container) {
        return;
      }
      const target = container.querySelector<HTMLElement>(`[data-tab-id="${tabId}"]`);
      if (target) {
        revealElement(target, overrideOptions);
      }
    },
    [revealElement],
  );

  const revealLastTab = useCallback(
    (overrideOptions?: TabRevealOptions) => {
      const container = containerRef.current;
      if (!container) {
        return;
      }
      const allTabs = container.querySelectorAll<HTMLElement>('[data-tab-id]');
      if (allTabs.length > 0) {
        const lastTab = allTabs[allTabs.length - 1];
        revealElement(lastTab, {
          revealPosition: 'end',
          ...overrideOptions,
        });
      }
    },
    [revealElement],
  );

  // 监听容器滚动
  useEffect(() => {
    const el = containerRef.current;
    if (!el) {
      return;
    }

    const handleScroll = () => {
      updateOverflow();
    };

    el.addEventListener('scroll', handleScroll, { passive: true });
    updateOverflow();

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        updateOverflow();
      });
      resizeObserver.observe(el);
    }

    return () => {
      el.removeEventListener('scroll', handleScroll);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
    };
  }, [updateOverflow]);

  // 当 activeTabId 改变时自动执行揭示
  useEffect(() => {
    if (options?.activeTabId) {
      revealTabById(options.activeTabId);
    }
  }, [options?.activeTabId, revealTabById]);

  return {
    containerRef,
    overflowState,
    updateOverflow,
    revealElement,
    revealTabById,
    revealLastTab,
  };
}
