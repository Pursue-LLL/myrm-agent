import { describe, it, expect } from 'vitest';
import {
  getNextNavIndex,
  calculateScrollRevealOffset,
  detectTabStripOverflow,
  formatAriaActiveDescendantId,
} from '../modelPickerKeyboardEngine';
import type { DOMRectLike, NavigableModelItem } from '../modelPickerKeyboardTypes';

describe('modelPickerKeyboardEngine', () => {
  describe('getNextNavIndex', () => {
    it('should return -1 when totalCount is 0 or all items are disabled', () => {
      expect(getNextNavIndex(0, 0, 'down')).toBe(-1);
      expect(getNextNavIndex(0, 3, 'down', () => true)).toBe(-1);
    });

    it('should advance index downwards and skip disabled items', () => {
      // 索引 1 被禁用，从 0 往下应跳到 2
      const isItemDisabled = (idx: number) => idx === 1;
      expect(getNextNavIndex(0, 3, 'down', isItemDisabled)).toBe(2);
      // 从 2 往下应循环回 0
      expect(getNextNavIndex(2, 3, 'down', isItemDisabled)).toBe(0);
    });

    it('should retreat index upwards and wrap around', () => {
      const isItemDisabled = (idx: number) => idx === 1;
      // 从 0 往上应循环到末尾 2
      expect(getNextNavIndex(0, 3, 'up', isItemDisabled)).toBe(2);
      // 从 2 往上应跳过 1 到 0
      expect(getNextNavIndex(2, 3, 'up', isItemDisabled)).toBe(0);
    });

    it('should jump to first enabled item on Home and last on End', () => {
      const isItemDisabled = (idx: number) => idx === 0 || idx === 4;
      expect(getNextNavIndex(2, 5, 'home', isItemDisabled)).toBe(1);
      expect(getNextNavIndex(2, 5, 'end', isItemDisabled)).toBe(3);
    });
  });

  describe('calculateScrollRevealOffset', () => {
    const containerRect: DOMRectLike = {
      left: 100,
      right: 500,
      width: 400,
      top: 0,
      bottom: 50,
      height: 50,
    };

    it('should not change scrollLeft when target is fully inside visible bounds', () => {
      const targetRect: DOMRectLike = {
        left: 200,
        right: 350,
        width: 150,
        top: 0,
        bottom: 50,
        height: 50,
      };
      const result = calculateScrollRevealOffset(containerRect, targetRect, 50, { safeMarginPx: 16 });
      expect(result).toBe(50);
    });

    it('should scroll right when target right exceeds container right', () => {
      const targetRect: DOMRectLike = {
        left: 450,
        right: 550, // 超过 container.right (500) 50px，加上 safeMargin 16px
        width: 100,
        top: 0,
        bottom: 50,
        height: 50,
      };
      const result = calculateScrollRevealOffset(containerRect, targetRect, 0, { safeMarginPx: 16 });
      // 550 + 16 - 500 = 66
      expect(result).toBe(66);
    });

    it('should scroll left when target left is cut off on the left', () => {
      const targetRect: DOMRectLike = {
        left: 50, // 小于 container.left (100)
        right: 180,
        width: 130,
        top: 0,
        bottom: 50,
        height: 50,
      };
      const result = calculateScrollRevealOffset(containerRect, targetRect, 100, { safeMarginPx: 16 });
      // container.left(100) - (target.left(50) - 16) = 66 => 100 - 66 = 34
      expect(result).toBe(34);
    });

    it('should center target when revealPosition is center', () => {
      const targetRect: DOMRectLike = {
        left: 200,
        right: 300,
        width: 100,
        top: 0,
        bottom: 50,
        height: 50,
      };
      // targetCenter in relative coords = (200 - 100) + 50 = 150
      // containerCenter = 400 / 2 = 200
      // delta = 150 - 200 = -50 => Math.max(0, 100 - 50) = 50
      const result = calculateScrollRevealOffset(containerRect, targetRect, 100, { revealPosition: 'center' });
      expect(result).toBe(50);
    });
  });

  describe('detectTabStripOverflow & formatAriaActiveDescendantId', () => {
    it('should calculate overflow and scroll capabilities correctly', () => {
      const overflow = detectTabStripOverflow(800, 400, 100);
      expect(overflow.isOverflowing).toBe(true);
      expect(overflow.canScrollLeft).toBe(true);
      expect(overflow.canScrollRight).toBe(true);
      expect(overflow.maxScrollLeft).toBe(400);

      const notOverflow = detectTabStripOverflow(350, 400, 0);
      expect(notOverflow.isOverflowing).toBe(false);
      expect(notOverflow.canScrollLeft).toBe(false);
      expect(notOverflow.canScrollRight).toBe(false);
    });

    it('should format aria active descendant id safely', () => {
      const items: NavigableModelItem[] = [
        { id: 'gpt-4o', providerId: 'openai', model: 'gpt-4o', label: 'GPT-4o' },
        { id: 'claude-3-7', providerId: 'anthropic', model: 'claude-3-7-sonnet', label: 'Claude 3.7' },
      ];

      expect(formatAriaActiveDescendantId('model-opt', 0, items)).toBe('model-opt-gpt-4o');
      expect(formatAriaActiveDescendantId('model-opt', 1, items)).toBe('model-opt-claude-3-7');
      expect(formatAriaActiveDescendantId('model-opt', -1, items)).toBeUndefined();
      expect(formatAriaActiveDescendantId('model-opt', 5, items)).toBeUndefined();
    });
  });
});
