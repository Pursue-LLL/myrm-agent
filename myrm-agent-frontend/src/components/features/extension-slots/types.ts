/**
 * [INPUT]
 * - react::ReactNode, ComponentType
 *
 * [OUTPUT]
 * - type ExtensionSlotName: 预定义的核心插槽名称
 * - interface ExtensionSlotContribution: 单个插槽贡献项契约
 * - interface ExtensionSlotStore: 插槽注册与查询状态接口
 *
 * [POS]
 * 声明式扩展插槽类型定义层。为 WebUI 各区域的原生扩展和插件挂载提供统一契约。
 */

import type { ComponentType, ReactNode } from 'react';

export type ExtensionSlotName =
  | 'sidebar.footer.action'
  | 'sidebar.header.action'
  | 'chat.header.actions'
  | 'settings.sections'
  | 'navbar.bottom.tools';

export interface ExtensionSlotContext {
  [key: string]: unknown;
}

export interface ExtensionSlotContribution<TContext extends ExtensionSlotContext = ExtensionSlotContext> {
  /** 插件项唯一标识 */
  id: string;
  /** 目标插槽名称 */
  slotName: ExtensionSlotName;
  /** 排序权重，数值越小越靠前 */
  order?: number;
  /** 挂载组件或渲染函数 */
  component: ComponentType<{ context?: TContext }>;
  /** 动态判断当前环境或状态下是否激活展示 */
  condition?: (context?: TContext) => boolean;
}

export interface ExtensionSlotState {
  contributions: ExtensionSlotContribution[];
  registerContribution: (contribution: ExtensionSlotContribution) => () => void;
  unregisterContribution: (id: string) => void;
  getContributionsForSlot: (slotName: ExtensionSlotName) => ExtensionSlotContribution[];
}
