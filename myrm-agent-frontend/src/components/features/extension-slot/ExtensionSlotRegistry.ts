/**
 * [INPUT]
 * - ./types.ts (POS: ExtensionSlotItem, ExtensionSlotName, ExtensionSlotContext)
 *
 * [OUTPUT]
 * - ExtensionSlotRegistry: 插槽注册中心单例
 * - extensionSlotRegistry: 默认实例
 * - useExtensionSlotItems: React Hook 用于订阅指定插槽项
 *
 * [POS]
 * 扩展插槽核心注册与分发引擎，支持动态装卸与优先级排序。
 */

import { useSyncExternalStore } from 'react';
import type {
  ExtensionSlotContext,
  ExtensionSlotItem,
  ExtensionSlotName,
} from './types';

type Listener = () => void;

export class ExtensionSlotRegistry {
  private items: Map<string, ExtensionSlotItem<any>> = new Map();
  private listeners: Set<Listener> = new Set();
  private snapshotVersion = 0;

  /**
   * 注册扩展插槽项
   * @returns unregister 清理函数
   */
  public register<T extends ExtensionSlotContext = ExtensionSlotContext>(
    item: ExtensionSlotItem<T>
  ): () => void {
    this.items.set(item.id, item);
    this.notify();

    return () => {
      if (this.items.has(item.id)) {
        this.items.delete(item.id);
        this.notify();
      }
    };
  }

  /**
   * 取消注册插槽项
   */
  public unregister(id: string): void {
    if (this.items.has(id)) {
      this.items.delete(id);
      this.notify();
    }
  }

  /**
   * 获取指定插槽的所有匹配项，按优先级排序并过滤不可见项
   */
  public getItems<T extends ExtensionSlotContext = ExtensionSlotContext>(
    slotName: ExtensionSlotName,
    context?: T
  ): ExtensionSlotItem<T>[] {
    const matched: ExtensionSlotItem<T>[] = [];

    for (const item of this.items.values()) {
      if (item.slotName === slotName) {
        if (!item.visible || item.visible(context)) {
          matched.push(item as ExtensionSlotItem<T>);
        }
      }
    }

    return matched.sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100));
  }

  /**
   * 获取快照版本号，供 useSyncExternalStore 使用
   */
  public getSnapshot = (): number => {
    return this.snapshotVersion;
  };

  /**
   * 订阅插槽注册表变更
   */
  public subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /**
   * 清空所有注册项（主要用于测试）
   */
  public clear(): void {
    this.items.clear();
    this.notify();
  }

  private notify(): void {
    this.snapshotVersion++;
    for (const listener of this.listeners) {
      try {
        listener();
      } catch (e) {
        console.error('Error in extension slot listener', e);
      }
    }
  }
}

export const extensionSlotRegistry = new ExtensionSlotRegistry();

/**
 * React Hook: 订阅并获取指定插槽的注册项
 */
export function useExtensionSlotItems<T extends ExtensionSlotContext = ExtensionSlotContext>(
  slotName: ExtensionSlotName,
  context?: T,
  registry: ExtensionSlotRegistry = extensionSlotRegistry
): ExtensionSlotItem<T>[] {
  useSyncExternalStore(
    registry.subscribe,
    registry.getSnapshot,
    registry.getSnapshot
  );

  return registry.getItems<T>(slotName, context);
}
