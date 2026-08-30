/**
 * [INPUT]
 * - React.ComponentType (POS: 插槽挂载组件类型)
 *
 * [OUTPUT]
 * - type ExtensionSlotName: 标准插槽枚举类型
 * - interface ExtensionSlotContext: 插槽运行时上下文
 * - interface ExtensionSlotItem: 插槽注册项契约
 *
 * [POS]
 * 前端声明式扩展插槽协议类型定义。
 */

import type { ComponentType, ReactNode } from 'react';

export type ExtensionSlotName =
  | 'sidebar.footer.action'
  | 'sidebar.header.extra'
  | 'chat.header.action'
  | 'chat.input.toolbar'
  | 'settings.general.extra'
  | 'app.status.bar'
  | (string & {});

export interface ExtensionSlotContext {
  isDesktop?: boolean;
  sessionId?: string;
  projectId?: string;
  [key: string]: unknown;
}

export interface ExtensionSlotItemProps<T extends ExtensionSlotContext = ExtensionSlotContext> {
  context?: T;
}

export interface ExtensionSlotItem<T extends ExtensionSlotContext = ExtensionSlotContext> {
  /** 唯一标识 */
  id: string;
  /** 目标插槽名称 */
  slotName: ExtensionSlotName;
  /** 渲染组件 */
  component: ComponentType<ExtensionSlotItemProps<T>>;
  /** 渲染优先级，数字越小越靠前（默认 100） */
  priority?: number;
  /** 可见性条件函数，返回 false 时不渲染 */
  visible?: (context?: T) => boolean;
}

export interface ExtensionSlotProps<T extends ExtensionSlotContext = ExtensionSlotContext> {
  name: ExtensionSlotName;
  context?: T;
  fallback?: ReactNode;
  className?: string;
  wrapperClassName?: string;
}
