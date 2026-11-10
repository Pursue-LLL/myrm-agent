/**
 * 消息高度缓存 Hook
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - React hooks: useState, useCallback
 *
 * [OUTPUT]
 * - useMessageHeights: 消息高度缓存 Hook
 *   - heightCache: Map<messageId, height>
 *   - setHeight(messageId, height): 设置消息高度
 *   - getHeight(messageId): 获取消息高度
 *   - clearCache(): 清空缓存
 *
 * [POS]
 * 消息高度缓存管理。在虚拟滚动中，消息高度用于计算滚动位置。
 * 通过缓存已测量的高度，避免重复测量，提高滚动性能。
 * Map 创建后不再替换，原地增删不触发重渲染。
 */

import { useState, useCallback } from 'react';

/** 高度缓存类型 */
type HeightCache = Map<string, number>;

/** Hook 返回类型 */
interface UseMessageHeightsReturn {
  /** 高度缓存 Map */
  heightCache: HeightCache;
  /** 设置消息高度 */
  setHeight: (messageId: string, height: number) => void;
  /** 获取消息高度 */
  getHeight: (messageId: string) => number | undefined;
  /** 清空缓存 */
  clearCache: () => void;
}

/**
 * 消息高度缓存 Hook
 *
 * 缓存是一个惰性创建、此后不再替换的 Map（只取 useState 的值，不取 setter），因为：
 * 1. 高度变化不需要触发组件重渲染
 * 2. 虚拟化器会自己调用 measure() 更新
 * 3. 避免性能问题（频繁 setState）
 */
export function useMessageHeights(): UseMessageHeightsReturn {
  const [cache] = useState<HeightCache>(() => new Map());

  const setHeight = useCallback(
    (messageId: string, height: number) => {
      cache.set(messageId, height);
    },
    [cache],
  );

  const getHeight = useCallback((messageId: string) => cache.get(messageId), [cache]);

  const clearCache = useCallback(() => {
    cache.clear();
  }, [cache]);

  return {
    heightCache: cache,
    setHeight,
    getHeight,
    clearCache,
  };
}
