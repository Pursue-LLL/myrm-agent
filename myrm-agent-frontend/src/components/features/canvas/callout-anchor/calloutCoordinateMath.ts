/**
 * Callout Coordinate & Viewport Math Engine
 * 空间锚点几何包围盒、视口平滑聚焦飞越矩阵与碰撞检测算法引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯算法纯函数设计，具备确定性与高性能。
 */

import {
  CalloutBoundingBox,
  ViewportTransform,
} from './calloutAnchorTypes';

const DEFAULT_PADDING = 40;
const MIN_SCALE = 0.75;
const MAX_SCALE = 2.5;

/**
 * 计算将目标构件平滑飞越并居中放置于视口中央的 Transform 矩阵
 */
export function calculateCenteringTransform(
  viewportWidth: number,
  viewportHeight: number,
  targetBox: CalloutBoundingBox,
  padding: number = DEFAULT_PADDING
): ViewportTransform {
  if (viewportWidth <= 0 || viewportHeight <= 0) {
    return { translateX: 0, translateY: 0, scale: 1 };
  }

  const availableWidth = Math.max(10, viewportWidth - padding * 2);
  const availableHeight = Math.max(10, viewportHeight - padding * 2);

  const scaleX = availableWidth / Math.max(1, targetBox.width);
  const scaleY = availableHeight / Math.max(1, targetBox.height);

  // 取宽高中更紧凑的缩放比，并 clamp 在安全显示区间内
  const rawScale = Math.min(scaleX, scaleY);
  const scale = Number(Math.max(MIN_SCALE, Math.min(MAX_SCALE, rawScale)).toFixed(3));

  const targetCenterX = targetBox.x + targetBox.width / 2;
  const targetCenterY = targetBox.y + targetBox.height / 2;

  const translateX = Math.round(viewportWidth / 2 - targetCenterX * scale);
  const translateY = Math.round(viewportHeight / 2 - targetCenterY * scale);

  return {
    translateX,
    translateY,
    scale,
  };
}

/**
 * 检测点 (x, y) 是否落在指定的包围盒内
 */
export function isPointInBox(
  x: number,
  y: number,
  box: CalloutBoundingBox
): boolean {
  return (
    x >= box.x &&
    x <= box.x + box.width &&
    y >= box.y &&
    y <= box.y + box.height
  );
}

/**
 * 计算欧几里得距离
 */
export function calculateDistance(
  x1: number,
  y1: number,
  x2: number,
  y2: number
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  return Math.sqrt(dx * dx + dy * dy);
}
