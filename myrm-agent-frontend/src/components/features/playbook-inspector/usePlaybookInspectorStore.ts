/**
 * [INPUT]
 * - ./playbookInspectorTypes::PlaybookRule, PlaybookStatus, PlaybookFilter
 * - zustand::create
 *
 * [OUTPUT]
 * - usePlaybookInspectorStore: 规约生命周期看板状态机
 *
 * [POS]
 * 判断力规约生命周期可视化仪表盘、胜率追溯与人工修正复活工作台的状态管理与仲裁操作层。
 */

import { create } from 'zustand';
import type { PlaybookRule, PlaybookFilter } from './playbookInspectorTypes';

const DEFAULT_INITIAL_RULES: PlaybookRule[] = [
  {
    id: 'pb-strict-typing',
    title: 'TypeScript 严格类型防御与禁用 any',
    triggerCondition: '生成或修改 TypeScript 代码、interface、type 契约时',
    directive: '严禁使用 any 类型，必须推导或显式声明精确类型；遇不确定数据优先使用 unknown + 类型收敛守卫。',
    status: 'active',
    triggerCount: 48,
    successCount: 45,
    winRate: 0.938,
    isPinned: true,
    recentFailures: [],
    lastTriggeredAt: Date.now() - 1000 * 60 * 15,
    updatedAt: Date.now() - 1000 * 60 * 60,
  },
  {
    id: 'pb-file-line-limit',
    title: '单文件 400 行严格行数边界控制与模块化拆分',
    triggerCondition: '新增或重构模块、文件超过 300 行时',
    directive: '单文件原则上不超过 400 行（最高 500 行）；超过时必须主动按单一职责拆分子模块，严禁暴力单文件臃肿。',
    status: 'degraded',
    triggerCount: 31,
    successCount: 20,
    winRate: 0.645,
    isPinned: false,
    recentFailures: [
      {
        sessionId: 'sess-code-gen-82',
        timestamp: Date.now() - 1000 * 60 * 120,
        errorSummary: '生成的复合控制器超过 480 行未触发拆分',
        contextSnippet: 'export class CompositeWorkflowController { ... 482 行 ... }',
      },
    ],
    lastTriggeredAt: Date.now() - 1000 * 60 * 120,
    updatedAt: Date.now() - 1000 * 60 * 120,
  },
  {
    id: 'pb-auto-cleanup-temp',
    title: '执行任务后自动删除临时调试文件',
    triggerCondition: '创建了 .tmp 或 scratch 测试脚本后',
    directive: '任务结束时自动扫描并清理临时调试文件。',
    status: 'retired',
    triggerCount: 14,
    successCount: 4,
    winRate: 0.286,
    isPinned: false,
    recentFailures: [
      {
        sessionId: 'sess-scratch-19',
        timestamp: Date.now() - 1000 * 60 * 60 * 24,
        errorSummary: '误删用户尚未持久化的草稿文件，触发负向反馈已自动退役',
        contextSnippet: 'rm -rf /workspace/scratch_draft.ts',
      },
    ],
    lastTriggeredAt: Date.now() - 1000 * 60 * 60 * 24,
    updatedAt: Date.now() - 1000 * 60 * 60 * 24,
  },
];

interface PlaybookInspectorState {
  rules: Record<string, PlaybookRule>;
  filter: PlaybookFilter;
  searchQuery: string;

  setFilter: (filter: PlaybookFilter) => void;
  setSearchQuery: (query: string) => void;
  reviveRule: (id: string) => void;
  togglePinRule: (id: string) => void;
  retireRule: (id: string) => void;
  updateRule: (
    id: string,
    updates: Partial<Pick<PlaybookRule, 'title' | 'triggerCondition' | 'directive'>>
  ) => void;
  addRule: (
    rule: Pick<PlaybookRule, 'title' | 'triggerCondition' | 'directive'>
  ) => PlaybookRule;
  setRules: (rules: PlaybookRule[]) => void;
  reset: () => void;
}

export const usePlaybookInspectorStore = create<PlaybookInspectorState>((set) => ({
  rules: Object.fromEntries(DEFAULT_INITIAL_RULES.map((r) => [r.id, r])),
  filter: 'all',
  searchQuery: '',

  setFilter: (filter: PlaybookFilter) => {
    set({ filter });
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query });
  },

  reviveRule: (id: string) => {
    set((state) => {
      const existing = state.rules[id];
      if (!existing) {
        return state;
      }
      return {
        rules: {
          ...state.rules,
          [id]: {
            ...existing,
            status: 'active',
            winRate: Math.max(existing.winRate, 0.8),
            updatedAt: Date.now(),
          },
        },
      };
    });
  },

  togglePinRule: (id: string) => {
    set((state) => {
      const existing = state.rules[id];
      if (!existing) {
        return state;
      }
      return {
        rules: {
          ...state.rules,
          [id]: {
            ...existing,
            isPinned: !existing.isPinned,
            updatedAt: Date.now(),
          },
        },
      };
    });
  },

  retireRule: (id: string) => {
    set((state) => {
      const existing = state.rules[id];
      if (!existing) {
        return state;
      }
      return {
        rules: {
          ...state.rules,
          [id]: {
            ...existing,
            status: 'retired',
            isPinned: false,
            updatedAt: Date.now(),
          },
        },
      };
    });
  },

  updateRule: (
    id: string,
    updates: Partial<Pick<PlaybookRule, 'title' | 'triggerCondition' | 'directive'>>
  ) => {
    set((state) => {
      const existing = state.rules[id];
      if (!existing) {
        return state;
      }
      return {
        rules: {
          ...state.rules,
          [id]: {
            ...existing,
            ...updates,
            updatedAt: Date.now(),
          },
        },
      };
    });
  },

  addRule: (
    rule: Pick<PlaybookRule, 'title' | 'triggerCondition' | 'directive'>
  ): PlaybookRule => {
    const id = `pb-custom-${Date.now()}`;
    const newRule: PlaybookRule = {
      id,
      title: rule.title.trim(),
      triggerCondition: rule.triggerCondition.trim(),
      directive: rule.directive.trim(),
      status: 'active',
      triggerCount: 0,
      successCount: 0,
      winRate: 1.0,
      isPinned: true,
      recentFailures: [],
      lastTriggeredAt: Date.now(),
      updatedAt: Date.now(),
    };
    set((state) => ({
      rules: { ...state.rules, [id]: newRule },
    }));
    return newRule;
  },

  setRules: (rules: PlaybookRule[]) => {
    set({
      rules: Object.fromEntries(rules.map((r) => [r.id, r])),
    });
  },

  reset: () => {
    set({
      rules: Object.fromEntries(DEFAULT_INITIAL_RULES.map((r) => [r.id, r])),
      filter: 'all',
      searchQuery: '',
    });
  },
}));
