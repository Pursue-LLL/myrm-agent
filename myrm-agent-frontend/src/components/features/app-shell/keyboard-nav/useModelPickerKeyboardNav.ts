/**
 * 模型选择器全键盘导航 Hook
 *
 * 劫持搜索输入框与列表键盘事件，提供上下循环漫游、Enter 确认、Escape 关闭与焦点视口对齐。
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import type { NavigableModelItem } from './modelPickerKeyboardTypes';
import { getNextNavIndex } from './modelPickerKeyboardEngine';

export interface UseModelPickerKeyboardNavOptions {
  items: NavigableModelItem[];
  isOpen: boolean;
  onSelect?: (item: NavigableModelItem) => void;
  onClose?: () => void;
  containerRef?: React.RefObject<HTMLElement | null>;
}

export function useModelPickerKeyboardNav({
  items,
  isOpen,
  onSelect,
  onClose,
  containerRef,
}: UseModelPickerKeyboardNavOptions) {
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  // 当弹窗打开或搜索结果列表改变时，重置或合理校正游标
  useEffect(() => {
    if (!isOpen) {
      setActiveIndex(-1);
      return;
    }

    // 默认高亮第一个可选项
    const firstEnabledIndex = items.findIndex((item) => !item.disabled);
    setActiveIndex(firstEnabledIndex);
  }, [isOpen, items]);

  // 当 activeIndex 变动时，确保对应项在滚动容器中完全可见
  useEffect(() => {
    if (activeIndex < 0 || !containerRef?.current) {
      return;
    }

    const container = containerRef.current;
    const activeEl = container.querySelector<HTMLElement>(`[data-nav-index="${activeIndex}"]`);
    if (activeEl && typeof activeEl.scrollIntoView === 'function') {
      activeEl.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
  }, [activeIndex, containerRef]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const currentItems = itemsRef.current;
      if (!isOpen || currentItems.length === 0) {
        return;
      }

      const isItemDisabled = (idx: number) => {
        return !!currentItems[idx]?.disabled;
      };

      switch (e.key) {
        case 'ArrowDown': {
          e.preventDefault();
          const nextIndex = getNextNavIndex(activeIndex, currentItems.length, 'down', isItemDisabled);
          if (nextIndex !== -1) {
            setActiveIndex(nextIndex);
          }
          break;
        }

        case 'ArrowUp': {
          e.preventDefault();
          const prevIndex = getNextNavIndex(activeIndex, currentItems.length, 'up', isItemDisabled);
          if (prevIndex !== -1) {
            setActiveIndex(prevIndex);
          }
          break;
        }

        case 'Home': {
          e.preventDefault();
          const homeIndex = getNextNavIndex(activeIndex, currentItems.length, 'home', isItemDisabled);
          if (homeIndex !== -1) {
            setActiveIndex(homeIndex);
          }
          break;
        }

        case 'End': {
          e.preventDefault();
          const endIndex = getNextNavIndex(activeIndex, currentItems.length, 'end', isItemDisabled);
          if (endIndex !== -1) {
            setActiveIndex(endIndex);
          }
          break;
        }

        case 'Enter': {
          if (activeIndex >= 0 && activeIndex < currentItems.length) {
            const currentItem = currentItems[activeIndex];
            if (!currentItem.disabled) {
              e.preventDefault();
              onSelect?.(currentItem);
            }
          }
          break;
        }

        case 'Escape': {
          e.preventDefault();
          onClose?.();
          break;
        }

        default:
          break;
      }
    },
    [isOpen, activeIndex, onSelect, onClose],
  );

  const activeItem = activeIndex >= 0 && activeIndex < items.length ? items[activeIndex] : undefined;

  return {
    activeIndex,
    activeItem,
    setActiveIndex,
    handleKeyDown,
  };
}
