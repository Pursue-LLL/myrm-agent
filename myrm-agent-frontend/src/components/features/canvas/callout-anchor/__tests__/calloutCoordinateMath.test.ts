import { describe, it, expect } from 'vitest';
import {
  calculateCenteringTransform,
  isPointInBox,
  calculateDistance,
} from '../calloutCoordinateMath';
import { CalloutBoundingBox } from '../calloutAnchorTypes';

describe('calloutCoordinateMath', () => {
  describe('calculateCenteringTransform', () => {
    it('当视口尺寸非法或为 0 时返回安全默认矩阵', () => {
      const box: CalloutBoundingBox = { x: 50, y: 50, width: 100, height: 100 };
      const transform = calculateCenteringTransform(0, 0, box);
      expect(transform).toEqual({ translateX: 0, translateY: 0, scale: 1 });
    });

    it('正确计算将目标构件居中对齐到视口中央的 Transform 矩阵', () => {
      const box: CalloutBoundingBox = { x: 80, y: 60, width: 90, height: 70 };
      const viewportWidth = 480;
      const viewportHeight = 320;

      const transform = calculateCenteringTransform(
        viewportWidth,
        viewportHeight,
        box
      );

      expect(transform.scale).toBeGreaterThanOrEqual(0.75);
      expect(transform.scale).toBeLessThanOrEqual(2.5);

      // 验证变换后，目标几何中心正好落在视口几何中心
      const targetCenterX = box.x + box.width / 2; // 80 + 45 = 125
      const targetCenterY = box.y + box.height / 2; // 60 + 35 = 95

      const transformedX = targetCenterX * transform.scale + transform.translateX;
      const transformedY = targetCenterY * transform.scale + transform.translateY;

      expect(Math.abs(transformedX - viewportWidth / 2)).toBeLessThanOrEqual(1);
      expect(Math.abs(transformedY - viewportHeight / 2)).toBeLessThanOrEqual(1);
    });
  });

  describe('isPointInBox', () => {
    const box: CalloutBoundingBox = { x: 10, y: 20, width: 50, height: 40 };

    it('点在包围盒内部时返回 true', () => {
      expect(isPointInBox(15, 25, box)).toBe(true);
      expect(isPointInBox(10, 20, box)).toBe(true); // 边界
      expect(isPointInBox(60, 60, box)).toBe(true); // 边界
    });

    it('点在包围盒外部时返回 false', () => {
      expect(isPointInBox(5, 25, box)).toBe(false);
      expect(isPointInBox(15, 65, box)).toBe(false);
      expect(isPointInBox(100, 100, box)).toBe(false);
    });
  });

  describe('calculateDistance', () => {
    it('正确计算两点之间的欧式几何距离', () => {
      expect(calculateDistance(0, 0, 3, 4)).toBe(5);
      expect(calculateDistance(10, 20, 10, 20)).toBe(0);
    });
  });
});
