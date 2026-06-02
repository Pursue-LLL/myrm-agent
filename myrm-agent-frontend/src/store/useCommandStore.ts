/**
 * Command Store - 管理用户自定义命令
 *
 * 存储策略（统一使用 ConfigSyncManager）：
 * - Tauri 模式（Desktop/WebUI）：同步到本地 SQLite
 * - Sandbox 模式：同步到云端 PostgreSQL
 * - 访客模式：仅保存到 localStorage，不同步
 *
 * 数据流：
 * 1. 初始化时从 ConfigSyncManager 加载
 * 2. 修改时乐观更新本地状态 + 通知 ConfigSyncManager
 * 3. ConfigSyncManager 负责防抖同步到后端
 */

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { SlashCommand, SlashAction, SlashItem } from '@/types/command';
import { getConfigSyncManager, type CommandsConfigValue } from '@/services/config';
import { buildBuiltinActions } from './builtinActions';

// 初始化标志
let isStoreInitialized = false;

interface CommandState {
  /** 用户自定义命令列表 */
  commands: SlashCommand[];

  /** 系统行为列表（未来扩展） */
  actions: SlashAction[];

  /** 最近使用的命令ID */
  recentCommandIds: string[];

  /** 是否已初始化 */
  isInitialized: boolean;

  /** 初始化命令 */
  initCommands: () => Promise<void>;

  /** 添加命令 */
  addCommand: (command: Omit<SlashCommand, 'id' | 'createdAt' | 'updatedAt' | 'type'>) => void;

  /** 更新命令 */
  updateCommand: (id: string, updates: Partial<Pick<SlashCommand, 'name' | 'template'>>) => void;

  /** 删除命令 */
  deleteCommand: (id: string) => void;

  /** 获取所有项（行为 + 命令） */
  getAllItems: () => SlashItem[];

  /** 搜索项 */
  searchItems: (query: string) => SlashItem[];

  /** 记录使用 */
  recordUsage: (id: string) => void;
}

/**
 * 同步到 ConfigSyncManager
 *
 * 统一通过 ConfigSyncManager 同步：
 * - Tauri 模式：TauriAdapter -> SQLite
 * - Sandbox 模式：SandboxAdapter -> PostgreSQL
 */
function syncToManager(commands: SlashCommand[], recentCommandIds: string[]): void {
  const value: CommandsConfigValue = {
    commands,
    recentCommandIds,
  };
  getConfigSyncManager().set('commands', value);
}

export const useCommandStore = create<CommandState>()(
  immer((set, get) => ({
    commands: [],
    actions: buildBuiltinActions(),
    recentCommandIds: [],
    isInitialized: false,

    initCommands: async () => {
      if (isStoreInitialized) return;

      try {
        // 从 ConfigSyncManager 加载
        const manager = getConfigSyncManager();
        await manager.initialize();

        const configValue = manager.get('commands');
        if (configValue) {
          set((state) => {
            state.commands = configValue.commands || [];
            state.recentCommandIds = configValue.recentCommandIds || [];
            state.isInitialized = true;
          });
        } else {
          set((state) => {
            state.commands = [];
            state.recentCommandIds = [];
            state.isInitialized = true;
          });
        }

        // 订阅变更（处理其他设备的同步）
        manager.subscribe('commands', (_key, value) => {
          const v = value as CommandsConfigValue;
          set((state) => {
            state.commands = v.commands || [];
            state.recentCommandIds = v.recentCommandIds || [];
          });
        });

        isStoreInitialized = true;
        console.log('[CommandStore] Initialized from ConfigSyncManager');
      } catch (error) {
        console.error('[CommandStore] Initialization failed:', error);
        set((state) => {
          state.commands = [];
          state.recentCommandIds = [];
          state.isInitialized = true;
        });
        isStoreInitialized = true;
      }
    },

    addCommand: (command) => {
      const newCommand: SlashCommand = {
        ...command,
        id: `cmd_${Date.now()}`,
        type: 'command',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      set((state) => {
        state.commands.push(newCommand);
      });

      // 同步到后端
      const { commands, recentCommandIds } = get();
      syncToManager(commands, recentCommandIds);
    },

    updateCommand: (id, updates) => {
      set((state) => {
        const index = state.commands.findIndex((cmd) => cmd.id === id);
        if (index !== -1) {
          state.commands[index] = {
            ...state.commands[index],
            ...updates,
            updatedAt: new Date().toISOString(),
          };
        }
      });

      // 同步到后端
      const { commands, recentCommandIds } = get();
      syncToManager(commands, recentCommandIds);
    },

    deleteCommand: (id) => {
      set((state) => {
        state.commands = state.commands.filter((cmd) => cmd.id !== id);
        state.recentCommandIds = state.recentCommandIds.filter((cmdId) => cmdId !== id);
      });

      // 同步到后端
      const { commands, recentCommandIds } = get();
      syncToManager(commands, recentCommandIds);
    },

    getAllItems: () => {
      const { actions, commands } = get();
      return [...actions, ...commands];
    },

    searchItems: (query) => {
      const items = get().getAllItems();
      const lowerQuery = query.toLowerCase();

      return items.filter((item) => {
        return item.name.toLowerCase().includes(lowerQuery);
      });
    },

    recordUsage: (id) => {
      set((state) => {
        // 移除旧记录
        state.recentCommandIds = state.recentCommandIds.filter((cmdId) => cmdId !== id);
        // 添加到开头
        state.recentCommandIds.unshift(id);
        // 限制最多10个
        state.recentCommandIds = state.recentCommandIds.slice(0, 10);
      });

      // 同步到后端（使用频率不高，可以同步）
      const { commands, recentCommandIds } = get();
      syncToManager(commands, recentCommandIds);
    },
  })),
);
