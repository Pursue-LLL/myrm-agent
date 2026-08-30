/**
 * [INPUT]
 * - zustand::create
 * - ./types::ExtensionSlotContribution, ExtensionSlotName, ExtensionSlotState
 *
 * [OUTPUT]
 * - useExtensionSlotStore: 全局插槽注册中心 Store
 *
 * [POS]
 * 扩展插槽状态管理中心。支持模块在挂载时动态注册插槽贡献项，并支持自动注销。
 */

import { create } from 'zustand';
import type { ExtensionSlotContribution, ExtensionSlotName, ExtensionSlotState } from './types';

export const useExtensionSlotStore = create<ExtensionSlotState>((set, get) => ({
  contributions: [],

  registerContribution: (contribution: ExtensionSlotContribution) => {
    set((state) => {
      const filtered = state.contributions.filter((c) => c.id !== contribution.id);
      return { contributions: [...filtered, contribution] };
    });

    return () => {
      get().unregisterContribution(contribution.id);
    };
  },

  unregisterContribution: (id: string) => {
    set((state) => ({
      contributions: state.contributions.filter((c) => c.id !== id),
    }));
  },

  getContributionsForSlot: (slotName: ExtensionSlotName) => {
    return get()
      .contributions.filter((c) => c.slotName === slotName)
      .sort((a, b) => (a.order ?? 100) - (b.order ?? 100));
  },
}));
