/**
 * Semantic Tool Group Zustand Store
 * 智能体权限能力语义组集中式状态管理与零终端配置策略
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any；
 * 2. 所有 if 必须包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import { create } from 'zustand';
import {
  AgentToolPolicyConfig,
  CompiledToolExecutionPolicy,
  SecurityPolicyLevel,
  SecurityPreset,
  ToolGroupId,
  ToolGroupState,
} from './semanticToolGroupTypes';
import {
  buildCompleteConfig,
  compileToolExecutionPolicy,
  PRESET_CONFIGS,
  SEMANTIC_TOOL_GROUPS,
} from './semanticToolGroupRegistry';

interface SemanticToolGroupStoreState {
  preset: SecurityPreset;
  groups: Record<ToolGroupId, ToolGroupState>;
  activeExpandedGroup: ToolGroupId | null;
  searchFilter: string;
  isExportDrawerOpen: boolean;

  // Actions
  setPreset: (preset: SecurityPreset) => void;
  toggleGroup: (groupId: ToolGroupId, enabled?: boolean) => void;
  setGroupSecurityLevel: (groupId: ToolGroupId, level: SecurityPolicyLevel) => void;
  toggleIndividualTool: (groupId: ToolGroupId, toolId: string) => void;
  setActiveExpandedGroup: (groupId: ToolGroupId | null) => void;
  setSearchFilter: (query: string) => void;
  setIsExportDrawerOpen: (open: boolean) => void;
  resetToDefault: () => void;
  exportConfigJson: () => string;
  importConfigJson: (jsonString: string) => { success: boolean; error?: string };
  getEffectivePolicy: () => CompiledToolExecutionPolicy;
  getCompleteConfig: () => AgentToolPolicyConfig;
}

const DEFAULT_PRESET: SecurityPreset = 'standard_assistant';

function createInitialGroups(preset: SecurityPreset): Record<ToolGroupId, ToolGroupState> {
  if (preset !== 'custom' && PRESET_CONFIGS[preset]) {
    return JSON.parse(JSON.stringify(PRESET_CONFIGS[preset])) as Record<ToolGroupId, ToolGroupState>;
  }

  const initial: Partial<Record<ToolGroupId, ToolGroupState>> = {};
  for (const group of SEMANTIC_TOOL_GROUPS) {
    initial[group.id] = {
      enabled: true,
      securityLevel: group.defaultSecurityLevel,
      disabledToolIds: group.tools.filter((t) => !t.isDefaultEnabled).map((t) => t.id),
    };
  }
  return initial as Record<ToolGroupId, ToolGroupState>;
}

export const useSemanticToolGroupStore = create<SemanticToolGroupStoreState>((set, get) => ({
  preset: DEFAULT_PRESET,
  groups: createInitialGroups(DEFAULT_PRESET),
  activeExpandedGroup: null,
  searchFilter: '',
  isExportDrawerOpen: false,

  setPreset: (preset: SecurityPreset) => {
    if (preset === 'custom') {
      set({ preset: 'custom' });
      return;
    }

    const template = PRESET_CONFIGS[preset];
    if (template) {
      set({
        preset,
        groups: JSON.parse(JSON.stringify(template)) as Record<ToolGroupId, ToolGroupState>,
      });
    }
  },

  toggleGroup: (groupId: ToolGroupId, enabled?: boolean) => {
    set((state) => {
      const current = state.groups[groupId];
      if (!current) {
        return state;
      }
      const nextEnabled = typeof enabled === 'boolean' ? enabled : !current.enabled;
      return {
        preset: 'custom',
        groups: {
          ...state.groups,
          [groupId]: {
            ...current,
            enabled: nextEnabled,
          },
        },
      };
    });
  },

  setGroupSecurityLevel: (groupId: ToolGroupId, level: SecurityPolicyLevel) => {
    set((state) => {
      const current = state.groups[groupId];
      if (!current) {
        return state;
      }
      return {
        preset: 'custom',
        groups: {
          ...state.groups,
          [groupId]: {
            ...current,
            securityLevel: level,
          },
        },
      };
    });
  },

  toggleIndividualTool: (groupId: ToolGroupId, toolId: string) => {
    set((state) => {
      const current = state.groups[groupId];
      if (!current) {
        return state;
      }

      const isDisabled = current.disabledToolIds.includes(toolId);
      const nextDisabledToolIds = isDisabled
        ? current.disabledToolIds.filter((id) => id !== toolId)
        : [...current.disabledToolIds, toolId];

      return {
        preset: 'custom',
        groups: {
          ...state.groups,
          [groupId]: {
            ...current,
            disabledToolIds: nextDisabledToolIds,
          },
        },
      };
    });
  },

  setActiveExpandedGroup: (groupId: ToolGroupId | null) => {
    set({ activeExpandedGroup: groupId });
  },

  setSearchFilter: (query: string) => {
    set({ searchFilter: query });
  },

  setIsExportDrawerOpen: (open: boolean) => {
    set({ isExportDrawerOpen: open });
  },

  resetToDefault: () => {
    set({
      preset: DEFAULT_PRESET,
      groups: createInitialGroups(DEFAULT_PRESET),
      activeExpandedGroup: null,
      searchFilter: '',
      isExportDrawerOpen: false,
    });
  },

  exportConfigJson: () => {
    const config = get().getCompleteConfig();
    return JSON.stringify(config, null, 2);
  },

  importConfigJson: (jsonString: string) => {
    try {
      const parsed = JSON.parse(jsonString) as unknown;
      if (!parsed || typeof parsed !== 'object') {
        return { success: false, error: '配置格式无效：必须是合法 JSON 对象' };
      }

      const config = parsed as Record<string, unknown>;
      if (!config.groups || typeof config.groups !== 'object') {
        return { success: false, error: '缺少 groups 核心字段' };
      }

      const incomingGroups = config.groups as Record<string, unknown>;
      const newGroups = { ...get().groups };

      for (const group of SEMANTIC_TOOL_GROUPS) {
        const item = incomingGroups[group.id];
        if (item && typeof item === 'object') {
          const typedItem = item as Record<string, unknown>;
          newGroups[group.id] = {
            enabled: Boolean(typedItem.enabled),
            securityLevel: (typedItem.securityLevel as SecurityPolicyLevel) || group.defaultSecurityLevel,
            disabledToolIds: Array.isArray(typedItem.disabledToolIds)
              ? (typedItem.disabledToolIds as string[])
              : [],
          };
        }
      }

      const incomingPreset = typeof config.preset === 'string' && ['strict_safe', 'standard_assistant', 'dev_expert', 'custom'].includes(config.preset)
        ? (config.preset as SecurityPreset)
        : 'custom';

      set({
        preset: incomingPreset,
        groups: newGroups,
      });

      return { success: true };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { success: false, error: `解析异常: ${message}` };
    }
  },

  getEffectivePolicy: () => {
    return compileToolExecutionPolicy(get().groups);
  },

  getCompleteConfig: () => {
    const state = get();
    return buildCompleteConfig(state.preset, state.groups);
  },
}));
