/**
 * 模型选择器全键盘导航与溢出标签栏末尾项自动揭示套件 - 类型定义
 *
 * 覆盖无鼠标键盘游标控制、无障碍属性规范以及横向标签栏视口溢出检测契约。
 */

export interface NavigableModelItem {
  id: string;
  providerId: string;
  model: string;
  label: string;
  disabled?: boolean;
  isSmartRouting?: boolean;
  isMoaPreset?: boolean;
  badge?: string;
  description?: string;
}

export type KeyboardNavDirection = 'down' | 'up' | 'home' | 'end';

export interface DOMRectLike {
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
}

export interface TabStripOverflowState {
  isOverflowing: boolean;
  canScrollLeft: boolean;
  canScrollRight: boolean;
  scrollLeft: number;
  maxScrollLeft: number;
}

export interface TabRevealOptions {
  safeMarginPx?: number;
  behavior?: ScrollBehavior;
  revealPosition?: 'nearest' | 'center' | 'end';
}
