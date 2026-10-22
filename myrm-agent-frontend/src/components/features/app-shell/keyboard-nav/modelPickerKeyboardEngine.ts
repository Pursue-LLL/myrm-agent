/**
 * 模型选择器全键盘导航与溢出标签栏末尾项自动揭示套件 - 计算引擎
 *
 * 纯函数实现全键盘循环游标计算、横向视口溢出检测与滚动揭示偏移量求解。
 */

import type {
  DOMRectLike,
  KeyboardNavDirection,
  NavigableModelItem,
  TabRevealOptions,
  TabStripOverflowState,
} from './modelPickerKeyboardTypes';

export const DEFAULT_TAB_SAFE_MARGIN_PX = 16;

/**
 * 求解下一个有效高亮项索引，自动避开已禁用的条目
 */
export function getNextNavIndex(
  currentIndex: number,
  totalCount: number,
  direction: KeyboardNavDirection,
  isItemDisabled?: (index: number) => boolean,
): number {
  if (totalCount <= 0) {
    return -1;
  }

  const checkDisabled = isItemDisabled ?? (() => false);

  // 检查是否所有条目均被禁用
  let allDisabled = true;
  for (let i = 0; i < totalCount; i++) {
    if (!checkDisabled(i)) {
      allDisabled = false;
      break;
    }
  }
  if (allDisabled) {
    return -1;
  }

  if (direction === 'home') {
    for (let i = 0; i < totalCount; i++) {
      if (!checkDisabled(i)) {
        return i;
      }
    }
    return -1;
  }

  if (direction === 'end') {
    for (let i = totalCount - 1; i >= 0; i--) {
      if (!checkDisabled(i)) {
        return i;
      }
    }
    return -1;
  }

  const step = direction === 'down' ? 1 : -1;
  let next = currentIndex;

  for (let attempt = 0; attempt < totalCount; attempt++) {
    next = (next + step + totalCount) % totalCount;
    if (!checkDisabled(next)) {
      return next;
    }
  }

  return -1;
}

/**
 * 求解标签栏目标项完全揭示所需的绝对 scrollLeft 偏移
 * 能够自动补足安全边距（safeMarginPx），防止最后一个标签被右侧操作按钮裁切
 */
export function calculateScrollRevealOffset(
  containerRect: DOMRectLike,
  targetRect: DOMRectLike,
  currentScrollLeft: number,
  options?: TabRevealOptions,
): number {
  const safeMargin = options?.safeMarginPx ?? DEFAULT_TAB_SAFE_MARGIN_PX;
  const position = options?.revealPosition ?? 'nearest';

  const containerVisibleLeft = containerRect.left;
  const containerVisibleRight = containerRect.right;

  // 目标项在容器坐标系中的相对位置
  const targetRelativeLeft = targetRect.left - containerVisibleLeft;
  const targetRelativeRight = targetRect.right - containerVisibleLeft;

  if (position === 'center') {
    const targetCenter = targetRelativeLeft + targetRect.width / 2;
    const containerCenter = containerRect.width / 2;
    return Math.max(0, currentScrollLeft + (targetCenter - containerCenter));
  }

  if (position === 'end') {
    // 强制右侧对齐并保留安全边距
    const delta = targetRelativeRight + safeMargin - containerRect.width;
    return Math.max(0, currentScrollLeft + delta);
  }

  // 'nearest' 模式：仅在超出边界时进行最小必要位移
  if (targetRect.right + safeMargin > containerVisibleRight) {
    // 右侧超出边界：向右滚动使其完整显示
    const overflowRight = targetRect.right + safeMargin - containerVisibleRight;
    return currentScrollLeft + overflowRight;
  }

  if (targetRect.left - safeMargin < containerVisibleLeft) {
    // 左侧超出边界：向左滚动使其完整显示
    const overflowLeft = containerVisibleLeft - (targetRect.left - safeMargin);
    return Math.max(0, currentScrollLeft - overflowLeft);
  }

  // 已经在完全可见区域内，无需滚动
  return currentScrollLeft;
}

/**
 * 检测横向标签栏容器的滚动溢出状态
 */
export function detectTabStripOverflow(
  scrollWidth: number,
  clientWidth: number,
  scrollLeft: number,
): TabStripOverflowState {
  const maxScrollLeft = Math.max(0, scrollWidth - clientWidth);
  const isOverflowing = scrollWidth > clientWidth + 1;
  const canScrollLeft = scrollLeft > 1;
  const canScrollRight = scrollLeft < maxScrollLeft - 1;

  return {
    isOverflowing,
    canScrollLeft,
    canScrollRight,
    scrollLeft,
    maxScrollLeft,
  };
}

/**
 * 格式化 aria-activedescendant 属性 ID
 */
export function formatAriaActiveDescendantId(
  prefix: string,
  activeIndex: number,
  items: NavigableModelItem[],
): string | undefined {
  if (activeIndex < 0 || activeIndex >= items.length) {
    return undefined;
  }
  const item = items[activeIndex];
  return `${prefix}-${item.id}`;
}
