/**
 * 开发者模式 Store
 *
 * 用于本地开发时覆盖部署模式，方便测试不同模式的效果
 * 仅在开发环境生效
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type DevModeOverride = 'none' | 'tauri' | 'local' | 'sandbox';

interface DevModeState {
  // 是否启用开发者模式覆盖
  enabled: boolean;

  // 覆盖的模式（none 表示不覆盖，使用实际检测结果）
  override: DevModeOverride;

  // 启用/禁用开发者模式
  setEnabled: (enabled: boolean) => void;

  // 设置覆盖模式
  setOverride: (override: DevModeOverride) => void;

  // 重置所有设置
  reset: () => void;

  // 获取是否应该覆盖为 Tauri 模式
  shouldOverrideAsTauri: () => boolean;

  // 获取是否应该覆盖为 Sandbox 模式
  shouldOverrideAsSandbox: () => boolean;
}

const DEFAULT_STATE = {
  enabled: false,
  override: 'none' as DevModeOverride,
};

export const useDevModeStore = create<DevModeState>()(
  persist(
    (set, get) => ({
      ...DEFAULT_STATE,

      setEnabled: (enabled: boolean) => {
        set({ enabled });
      },

      setOverride: (override: DevModeOverride) => {
        set({ override });
      },

      reset: () => {
        set(DEFAULT_STATE);
      },

      shouldOverrideAsTauri: () => {
        const { enabled, override } = get();
        return enabled && override === 'tauri';
      },

      shouldOverrideAsSandbox: () => {
        const { enabled, override } = get();
        return enabled && override === 'sandbox';
      },
    }),
    {
      name: 'dev-mode-storage',
    },
  ),
);
