/**
 * [INPUT]
 * - items: OutlineTurnItem[] (POS: 轮次大纲项目列表)
 * - activeViewportTurn: number | null (POS: 当前视口正在浏览的轮次索引)
 * - hoveredTurnIndex?: number | null (POS: 鼠标悬浮预览引力中心)
 *
 * [OUTPUT]
 * - geometries: StaircaseGeometryItem[] (POS: 每个轮次刻度的阶梯几何尺寸与不透明度)
 *
 * [POS]
 * 阶梯缩放几何学 (Staircase Scale Geometry) 纯函数与 Hook 引擎。
 * 距离当前视口/鼠标引力中心越近，刻度越长越饱满，呈现丝滑聚焦透视感。
 * 严格类型：零 `any`。文件行数 < 120 行。
 */

import { useMemo } from 'react';
import type { OutlineTurnItem, StaircaseGeometryItem } from './outlineTypes';

export interface UseOutlineGeometryOptions {
  items: OutlineTurnItem[];
  activeViewportTurn: number | null;
  hoveredTurnIndex?: number | null;
}

/**
 * 纯数学函数：计算单一轮次的阶梯缩放几何参数
 */
export function computeStaircaseGeometry(
  turnIndex: number,
  focusTurn: number,
): StaircaseGeometryItem {
  const distance = Math.abs(turnIndex - focusTurn);
  const isCenter = distance === 0;

  if (isCenter) {
    return {
      turnIndex,
      scale: 1.0,
      width: 24,
      height: 4,
      opacity: 1.0,
      isCenter: true,
      distanceFromActive: 0,
    };
  }

  if (distance === 1) {
    return {
      turnIndex,
      scale: 0.82,
      width: 18,
      height: 3,
      opacity: 0.85,
      isCenter: false,
      distanceFromActive: 1,
    };
  }

  if (distance === 2) {
    return {
      turnIndex,
      scale: 0.68,
      width: 13,
      height: 2.5,
      opacity: 0.65,
      isCenter: false,
      distanceFromActive: 2,
    };
  }

  // distance >= 3: 平滑渐近微缩
  const minScale = 0.5;
  const falloff = Math.max(0, 0.15 - (distance - 3) * 0.02);
  const scale = Number((minScale + falloff).toFixed(3));
  const width = Math.max(8, Math.round(10 - (distance - 3) * 0.4));
  const height = 2;
  const opacity = Number(Math.max(0.3, 0.5 - distance * 0.025).toFixed(2));

  return {
    turnIndex,
    scale,
    width,
    height,
    opacity,
    isCenter: false,
    distanceFromActive: distance,
  };
}

export function useOutlineGeometry({
  items,
  activeViewportTurn,
  hoveredTurnIndex,
}: UseOutlineGeometryOptions): StaircaseGeometryItem[] {
  return useMemo(() => {
    if (!items || items.length === 0) {
      return [];
    }

    // 引力焦点：悬浮轮次优先，其次当前视口轮次，最后默认为末尾最新轮次
    const defaultTurn = items[items.length - 1]?.turnIndex ?? 1;
    const focusTurn =
      typeof hoveredTurnIndex === 'number' && hoveredTurnIndex > 0
        ? hoveredTurnIndex
        : typeof activeViewportTurn === 'number' && activeViewportTurn > 0
        ? activeViewportTurn
        : defaultTurn;

    return items.map((item) => computeStaircaseGeometry(item.turnIndex, focusTurn));
  }, [items, activeViewportTurn, hoveredTurnIndex]);
}
